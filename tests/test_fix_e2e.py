"""``--fix``, ``--diff`` and ``--add-foqa`` end to end (SPEC §4.4, §5.2, §5.3, §6.1)."""

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

from furryp.core.diagnostic import Diagnostic, Edit, Fix, line_span
from furryp.core.registry import Rule, RuleContext, Scope
from furryp.rules import ALL_RULES
from tests.support import (
    CONFIG,
    FLAGGED,
    PYPROJECT,
    TempDirTestCase,
    run_furryp,
    run_furryp_raw,
    run_main,
    write_files,
)

ALL_PASSED = "All checks passed!\n"
BROKEN = "x = (\n"
UNUSED = "  # foqa:FUR102"


class E2eTestCase(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        write_files(self.root, {PYPROJECT: ""})

    def read(self, name: str) -> bytes:
        return (self.root / name).read_bytes()


class FixTest(E2eTestCase):
    def test_fix_is_idempotent(self) -> None:
        write_files(self.root, {"a.py": f"x = 1{UNUSED}\n", "b.py": f"y = 2{UNUSED}\n"})
        result = run_furryp(["check", "--fix"], self.root)
        self.assertEqual(
            (result.returncode, result.stdout, result.stderr),
            (0, "Found 2 errors (2 fixed, 0 remaining).\n", ""),
        )
        self.assertEqual(self.read("a.py"), b"x = 1\n")
        self.assertEqual(self.read("b.py"), b"y = 2\n")
        result = run_furryp(["check", "--fix"], self.root)
        self.assertEqual((result.returncode, result.stdout), (0, ALL_PASSED))
        self.assertEqual(self.read("a.py"), b"x = 1\n")

    def test_remaining_diagnostics_are_shown(self) -> None:
        write_files(self.root, {"a.py": f"y = 1{UNUSED}\n{FLAGGED}\n", "c.py": BROKEN})
        result = run_furryp(["check", "--fix"], self.root)
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.startswith("demeter-chain [FUR403]: "))
        self.assertIn("invalid-syntax [FUR000]: ", result.stdout)
        self.assertTrue(
            result.stdout.endswith("\n\nFound 3 errors (1 fixed, 2 remaining).\n")
        )
        self.assertEqual(self.read("a.py"), f"y = 1\n{FLAGGED}\n".encode())
        self.assertEqual(self.read("c.py"), BROKEN.encode())

    def test_nothing_fixed_keeps_the_plain_footer(self) -> None:
        """As ruff: no ``(… fixed, … remaining)`` when no fix was applied."""
        write_files(self.root, {"c.py": BROKEN})
        result = run_furryp(["check", "--fix"], self.root)
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.endswith("\n\nFound 1 error.\n"))
        self.assertEqual(
            run_furryp(["check", "--fix", "--exit-zero"], self.root).returncode, 0
        )

    def test_write_error_is_reported_and_the_other_files_are_fixed(self) -> None:
        write_files(self.root, {"a.py": f"x = 1{UNUSED}\n", "b.py": f"y = 2{UNUSED}\n"})
        real_write = Path.write_bytes

        def write_bytes(path: Path, data: bytes) -> int:
            if path.name == "a.py":
                raise PermissionError(13, "Permission denied")
            return real_write(path, data)

        with mock.patch.object(Path, "write_bytes", write_bytes):
            code, out, err = run_main(["check", "--fix"], self.root)
        self.assertEqual(code, 2)
        self.assertEqual(
            err,
            "error: Failed to check a.py: PermissionError: [Errno 13] Permission denied\n",
        )
        self.assertEqual(out, "Found 1 error (1 fixed, 0 remaining).\n")
        self.assertEqual(self.read("a.py"), f"x = 1{UNUSED}\n".encode())
        self.assertEqual(self.read("b.py"), b"y = 2\n")

    def test_encodings_and_line_breaks_are_kept_byte_for_byte(self) -> None:
        files = {
            "crlf.py": b"x = 1  # foqa:FUR102\r\ny = 2\r\n",
            "bom.py": b"\xef\xbb\xbfname = '\xc3\xa9t\xc3\xa9'  # foqa:FUR102\n",
            "mixed.py": b"x = 1  # foqa:FUR102\r\ny = 2\nz = 3\r\r\n",
            "latin.py": b"# -*- coding: latin-1 -*-\nname = '\xe9t\xe9'  # foqa:FUR102\n",
        }
        write_files(self.root, files)
        self.assertEqual(run_furryp(["check", "--fix"], self.root).returncode, 0)
        self.assertEqual(self.read("crlf.py"), b"x = 1\r\ny = 2\r\n")
        self.assertEqual(
            self.read("bom.py"), b"\xef\xbb\xbfname = '\xc3\xa9t\xc3\xa9'\n"
        )
        self.assertEqual(self.read("mixed.py"), b"x = 1\r\ny = 2\nz = 3\r\r\n")
        self.assertEqual(
            self.read("latin.py"), b"# -*- coding: latin-1 -*-\nname = '\xe9t\xe9'\n"
        )


class DiffTest(E2eTestCase):
    def test_diff_writes_nothing(self) -> None:
        write_files(self.root, {"b.py": f"y = 2{UNUSED}\n", "a.py": f"x = 1{UNUSED}\n"})
        result = run_furryp(["check", "--diff"], self.root)
        self.assertEqual((result.returncode, result.stderr), (1, ""))
        self.assertEqual(
            result.stdout,
            f"--- a.py\n+++ a.py\n@@ -1 +1 @@\n-x = 1{UNUSED}\n+x = 1\n"
            "\n"
            f"--- b.py\n+++ b.py\n@@ -1 +1 @@\n-y = 2{UNUSED}\n+y = 2\n"
            "\n"
            "Would fix 2 errors.\n",
        )
        self.assertEqual(self.read("a.py"), f"x = 1{UNUSED}\n".encode())
        self.assertEqual(self.read("b.py"), f"y = 2{UNUSED}\n".encode())
        result = run_furryp(["check", "--diff", "--exit-zero"], self.root)
        self.assertEqual(result.returncode, 0)

    def test_nothing_to_fix_prints_nothing(self) -> None:
        """As ruff with E902 selected, the only case of furryp: FUR000 is always
        active. No output and exit 0, even with violations left."""
        write_files(
            self.root, {"a.py": "x = 1\n", "c.py": BROKEN, "f.py": f"{FLAGGED}\n"}
        )
        for paths in (
            ["a.py"],
            ["c.py"],
            ["f.py"],
            ["missing.py"],
            ["--select", "FUR403", "missing.py"],
        ):
            with self.subTest(paths=paths):
                result = run_furryp(["check", "--diff", *paths], self.root)
                self.assertEqual(
                    (result.returncode, result.stdout, result.stderr), (0, "", "")
                )

    def test_diff_keeps_the_line_breaks(self) -> None:
        """Raw bytes: only the lines of the file end with ``\\r\\n`` (ruff)."""
        write_files(self.root, {"a.py": b"x = 1\r\ny = 2  # foqa:FUR102\r\n"})
        result = run_furryp_raw(["check", "--diff"], self.root)
        self.assertEqual(
            result.stdout,
            b"--- a.py\n+++ a.py\n@@ -1,2 +1,2 @@\n x = 1\r\n"
            b"-y = 2  # foqa:FUR102\r\n+y = 2\r\n"
            b"\nWould fix 1 error.\n",
        )


class AddFoqaTest(E2eTestCase):
    def test_add_foqa_then_check_passes(self) -> None:
        write_files(
            self.root,
            {
                "a.py": f"{FLAGGED}\n",
                "b.py": "y = 2\nz = 3\nw = 4\n",
                "c.py": BROKEN,
                CONFIG: json.dumps({"rules": {"file-too-long": {"max-lines": 2}}}),
            },
        )
        result = run_furryp(["check", "--add-foqa", "a.py", "b.py", "c.py"], self.root)
        self.assertEqual(
            (result.returncode, result.stdout, result.stderr),
            (0, "", "Added 2 foqa directives.\n"),
        )
        self.assertEqual(self.read("a.py"), f"{FLAGGED}  # foqa:FUR403\n".encode())
        self.assertEqual(
            self.read("b.py"), b"# furryp: foqa:FUR102\ny = 2\nz = 3\nw = 4\n"
        )
        self.assertEqual(self.read("c.py"), BROKEN.encode())
        result = run_furryp(["check", "a.py", "b.py"], self.root)
        self.assertEqual((result.returncode, result.stdout), (0, ALL_PASSED))
        result = run_furryp(["check", "--add-foqa", "a.py", "b.py"], self.root)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
        self.assertEqual(self.read("a.py"), f"{FLAGGED}  # foqa:FUR403\n".encode())


class DirectiveWarningTest(E2eTestCase):
    """On stderr, whatever the mode, and without effect on the exit code (ruff)."""

    INVALID = (
        "warning: Invalid `# foqa` directive on a.py:1: expected `:` followed by a"
        " comma-separated list of codes (e.g., `# foqa:FUR101,FUR403`).\n"
    )

    def setUp(self) -> None:
        super().setUp()
        write_files(self.root, {"a.py": "x = 1  # foqa.\n"})

    def test_check(self) -> None:
        result = run_furryp(["check", "a.py"], self.root)
        self.assertEqual(
            (result.returncode, result.stdout, result.stderr),
            (0, ALL_PASSED, self.INVALID),
        )

    def test_with_violations_and_exit_zero(self) -> None:
        write_files(self.root, {"a.py": f"{FLAGGED}  # foqa.\n"})
        result = run_furryp(["check", "a.py"], self.root)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, self.INVALID)
        self.assertIn("demeter-chain [FUR403]", result.stdout)
        result = run_furryp(["check", "--exit-zero", "a.py"], self.root)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, self.INVALID)

    def test_even_if_the_rules_are_not_selected(self) -> None:
        result = run_furryp(["check", "--select", "FUR102", "a.py"], self.root)
        self.assertEqual((result.returncode, result.stderr), (0, self.INVALID))

    def test_modes_that_read_the_file_once(self) -> None:
        report = str(self.root / "out.html")
        for option in (
            ["--statistics"],
            ["--fix"],
            ["--diff"],
            ["--add-foqa"],
            ["--report-html", report],
        ):
            with self.subTest(option=option):
                result = run_furryp(["check", *option, "a.py"], self.root)
                self.assertEqual(result.stderr, self.INVALID)

    def test_again_at_each_pass_of_the_fixes(self) -> None:
        # As ruff 0.17.3: a directive still there after a pass warns again.
        text = "x = 1  # foqa.\ny = 1  # foqa:FUR102\n"
        for option in ("--fix", "--diff"):
            with self.subTest(option=option):
                write_files(self.root, {"a.py": text})
                result = run_furryp(["check", option, "a.py"], self.root)
                self.assertEqual(result.stderr, self.INVALID * 2)

    def test_add_foqa_is_not_idempotent_after_an_invalid_directive(self) -> None:
        # As --add-noqa of ruff 0.17.3: it stops at the invalid directive.
        write_files(self.root, {"a.py": f"{FLAGGED}  # foqa.\n"})
        for count in (1, 2):
            run_furryp(["check", "--add-foqa", "a.py"], self.root)
            expected = f"{FLAGGED}  # foqa." + "  # foqa:FUR403" * count + "\n"
            self.assertEqual(self.read("a.py"), expected.encode())


def open_bracket(context: RuleContext[Any]) -> Iterator[Diagnostic]:
    """Fake rule whose fix breaks the syntax of every file."""
    source = context.source
    fix = Fix((Edit(0, 0, "("),))
    yield Diagnostic(
        "FUR998", "breaker", "m", source.path, line_span(1, 1, 2), "Do", fix
    )


BREAKER = Rule(
    "FUR998", "breaker", "errors", "Fake.", None, True, Scope.LINE, open_bracket
)


class RevertTest(E2eTestCase):
    def test_fix_that_breaks_the_syntax_is_reverted(self) -> None:
        write_files(self.root, {"pkg/a.py": "x = 1\n"})
        with mock.patch("furryp.cli.app.ALL_RULES", [*ALL_RULES, BREAKER]):
            code, out, err = run_main(["check", "--fix"], self.root)
        path = os.path.join("pkg", "a.py")
        self.assertEqual(
            err, f"error: Fix introduced a syntax error in {path}; reverting\n"
        )
        self.assertEqual(code, 1)
        self.assertIn("breaker [FUR998] [*]: m\n", out)
        self.assertTrue(out.endswith("Found 1 error.\n[*] 1 fixable with `--fix`.\n"))
        self.assertEqual(self.read("pkg/a.py"), b"x = 1\n")
