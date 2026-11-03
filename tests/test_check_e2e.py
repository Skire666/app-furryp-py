"""``furryp check`` for CI: exit codes, encodings, internal errors (SPEC §4.4, §5.7)."""

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

from furryp.core.diagnostic import Diagnostic, line_span
from furryp.core.registry import Rule, RuleContext, Scope
from furryp.rules import ALL_RULES
from tests.support import (
    CONFIG,
    PYPROJECT,
    REPO_ROOT,
    TempDirTestCase,
    run_furryp,
    run_main,
    unreadable_directory,
    write_files,
)

CLEAN = "x = 1\n"
CHAIN = "x = a.b.c.d.e\n"
ALL_PASSED = "All checks passed!\n"
NO_FILES = "warning: No Python files found under the given path(s)\n"


class CiTest(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        write_files(self.root, {PYPROJECT: ""})

    def test_missing_path(self) -> None:
        write_files(self.root, {"a.py": CLEAN})
        result = run_furryp(["check", "a.py", "missing.py"], self.root)
        self.assertEqual((result.returncode, result.stderr), (1, ""))
        self.assertEqual(
            result.stdout,
            "invalid-syntax [FUR000]: Failed to read file: No such file or directory\n"
            "--> missing.py:1:1\n"
            "help: Check that the path exists and is readable\n"
            "\n"
            "Found 1 error.\n",
        )

    def test_missing_path_cannot_be_hidden(self) -> None:
        result = run_furryp(
            ["check", "missing", "--ignore", "FUR", "--exit-zero"], self.root
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("invalid-syntax [FUR000]", result.stdout)
        result = run_furryp(["check", "missing", "--ignore", "FUR"], self.root)
        self.assertEqual(result.returncode, 1)

    def test_no_python_files(self) -> None:
        write_files(self.root, {"docs/readme.txt": "x"})
        result = run_furryp(["check", "docs"], self.root)
        self.assertEqual(
            (result.returncode, result.stdout, result.stderr), (0, ALL_PASSED, NO_FILES)
        )

    def test_unreadable_directory_is_a_warning(self) -> None:
        """As ruff 0.17.3: a warning on stderr, exit code 0, no FUR000."""
        write_files(self.root, {"locked/a.py": CHAIN, "pkg/b.py": CLEAN})
        warning = f"warning: Encountered error: {Path('locked')}: Permission denied\n"
        with unreadable_directory(self.root / "locked"):
            self.assertEqual(
                run_main(["check", "locked"], self.root), (0, ALL_PASSED, warning)
            )
            self.assertEqual(
                run_main(["check", "."], self.root), (0, ALL_PASSED, warning)
            )
        write_files(self.root, {"pkg/c.py": CHAIN})
        with unreadable_directory(self.root / "locked"):
            code, out, err = run_main(["check"], self.root)
        self.assertEqual((code, err), (1, warning))
        self.assertTrue(out.endswith("Found 1 error.\n"))

    def test_violations(self) -> None:
        write_files(self.root, {"pkg/a.py": CHAIN, "pkg/b.py": CLEAN})
        result = run_furryp(["check"], self.root)
        self.assertEqual(result.returncode, 1)
        self.assertTrue(
            result.stdout.startswith(
                "demeter-chain [FUR403]: Attribute chain `a.b.c.d.e` is too deep (4 > 3)\n"
            )
        )
        self.assertIn(f" --> pkg{os.sep}a.py:1:5\n", result.stdout)
        self.assertTrue(result.stdout.endswith("\n\nFound 1 error.\n"))
        result = run_furryp(["check", "--exit-zero"], self.root)
        self.assertEqual(result.returncode, 0)

    def test_statistics(self) -> None:
        write_files(
            self.root,
            {"a.py": CHAIN, "b.py": CHAIN, "c.py": "x = 1  # foqa:FUR102\n"},
        )
        result = run_furryp(["check", "--statistics"], self.root)
        self.assertEqual((result.returncode, result.stderr), (1, ""))
        self.assertEqual(
            result.stdout,
            "2\tFUR403\t[ ] demeter-chain\n"
            "1\tFUR001\t[*] unused-foqa\n"
            "Found 3 errors.\n"
            "[*] 1 fixable with `--fix`.\n",
        )
        write_files(self.root, {"a.py": CLEAN, "b.py": CLEAN, "c.py": CLEAN})
        result = run_furryp(["check", "--statistics"], self.root)
        self.assertEqual((result.returncode, result.stdout), (0, ""))


class EncodingTest(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        write_files(self.root, {PYPROJECT: ""})

    def test_utf8_output_with_a_cp1252_console(self) -> None:
        write_files(self.root, {"é.py": "flèche = a.b.c.d.e  # → 日本\n"})
        result = run_furryp(["check"], self.root, {"PYTHONIOENCODING": "cp1252"})
        self.assertEqual(result.returncode, 1)
        self.assertIn(" --> é.py:1:10\n", result.stdout)
        self.assertIn(
            "1 | flèche = a.b.c.d.e  # → 日本\n  |          " + "^" * 9 + "\n",
            result.stdout,
        )

    def test_latin1_source(self) -> None:
        data = "# -*- coding: latin-1 -*-\nété = a.b.c.d.e\n".encode("latin-1")
        write_files(self.root, {"legacy.py": data})
        result = run_furryp(["check"], self.root)
        self.assertEqual((result.returncode, result.stderr), (1, ""))
        self.assertIn(
            "1 | # -*- coding: latin-1 -*-\n2 | été = a.b.c.d.e\n  |       ^^^^^^^^^\n",
            result.stdout,
        )
        self.assertEqual((self.root / "legacy.py").read_bytes(), data)

    def test_undecodable_source(self) -> None:
        write_files(self.root, {"bad.py": b'name = "\xe9t\xe9"\n'})
        result = run_furryp(["check"], self.root)
        self.assertEqual(result.returncode, 1)
        self.assertTrue(
            result.stdout.startswith(
                "invalid-syntax [FUR000]: Failed to decode file: "
                "invalid or missing encoding declaration\n"
                "--> bad.py:1:1\n"
                "help: Save the file as UTF-8"
            ),
            result.stdout,
        )

    def test_codec_that_is_not_a_text_encoding(self) -> None:
        write_files(self.root, {"rot.py": "# -*- coding: rot13 -*-\nx = 1\n"})
        result = run_furryp(["check"], self.root)
        self.assertEqual((result.returncode, result.stderr), (1, ""))
        self.assertTrue(
            result.stdout.startswith(
                "invalid-syntax [FUR000]: Failed to decode file: "
            ),
            result.stdout,
        )
        self.assertIn("\n--> rot.py:1:1\nhelp: Save the file as UTF-8", result.stdout)

    def test_output_line_endings_are_lf_on_every_platform(self) -> None:
        write_files(self.root, {"a.py": CHAIN})
        env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
        result = subprocess.run(
            [sys.executable, "-m", "furryp", "check", "missing.py"],
            cwd=self.root,
            env=env,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"\n--> missing.py:1:1\n", result.stdout)
        self.assertNotIn(b"\r", result.stdout)
        result = subprocess.run(
            [sys.executable, "-m", "furryp", "check", "--bogus"],
            cwd=self.root,
            env=env,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr.startswith(b"error: "))
        self.assertNotIn(b"\r", result.stderr)


def explode(context: RuleContext[Any]) -> Iterator[Diagnostic]:
    """Fake rule failing on ``boom.py`` and reporting every other file."""
    if context.source.path.name == "boom.py":
        raise RuntimeError("boom")
    yield Diagnostic(
        "FUR999", "explode", "m", context.source.path, line_span(1, 1, 2), "Do it"
    )


EXPLODING = Rule(
    "FUR999", "explode", "errors", "Fake.", None, False, Scope.LINE, explode
)


class InternalErrorTest(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        write_files(
            self.root,
            {PYPROJECT: "", "a.py": CLEAN, "boom.py": CLEAN},
        )

    def run_check(self, *args: str) -> tuple[int, str, str]:
        with mock.patch("furryp.cli.app.ALL_RULES", [*ALL_RULES, EXPLODING]):
            return run_main(["check", *args], self.root)

    def test_violations_and_internal_error(self) -> None:
        code, out, err = self.run_check()
        self.assertEqual(code, 2)
        self.assertEqual(err, "error: Failed to check boom.py: RuntimeError: boom\n")
        self.assertIn("explode [FUR999]: m\n --> a.py:1:1\n", out)
        self.assertTrue(out.endswith("Found 1 error.\n"))

    def test_exit_zero_does_not_hide_errors(self) -> None:
        self.assertEqual(self.run_check("--exit-zero")[0], 2)
        self.assertEqual(self.run_check("--statistics")[0], 2)

    def test_internal_error_without_violations(self) -> None:
        code, out, err = self.run_check("boom.py")
        self.assertEqual((code, out), (2, ALL_PASSED))
        self.assertEqual(err, "error: Failed to check boom.py: RuntimeError: boom\n")


class PathTest(TempDirTestCase):
    def test_paths_outside_the_current_directory_are_absolute(self) -> None:
        project = self.root / "project"
        write_files(project, {PYPROJECT: "", "sub/a.py": CLEAN})
        write_files(self.root, {"outside.py": CHAIN})
        result = run_furryp(
            ["check", str(Path("..", "..", "outside.py"))], project / "sub"
        )
        self.assertIn(f" --> {self.root / 'outside.py'}:1:5\n", result.stdout)
