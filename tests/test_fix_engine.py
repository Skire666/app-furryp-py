"""Fix engine: selection, passes, revert, writing (SPEC §7.2)."""

import unittest
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

from furryp.core.diagnostic import Diagnostic, Edit, Fix, line_span
from furryp.core.registry import Rule, RuleContext, Scope
from furryp.fix.engine import (
    FixResult,
    apply_edits,
    fix_path,
    fix_report,
    select_fixes,
    write_fixes,
)
from tests.support import TempDirTestCase, linter_with, text_source, write_files

UNUSED = "  # foqa:FUR102"


def fix_text(
    text: str, rules: tuple[Rule, ...] = (), data: dict[str, object] | None = None
) -> FixResult:
    """Fix ``text`` in memory with the shipped rules plus ``rules``."""
    linter = linter_with(rules, data)
    return fix_report(linter, linter.check_source(text_source(text)))


def fake_rule(code: str, edit: Any) -> Rule:
    """Return a fake rule whose fix is ``edit(text)`` (no diagnostic if ``None``)."""

    def check(context: RuleContext[Any]) -> Iterator[Diagnostic]:
        source = context.source
        found = edit(source.text)
        if found is not None:
            span = line_span(1, 1, 1)
            yield Diagnostic(code, "fake", "m", source.path, span, "Do", Fix((found,)))

    return Rule(code, f"fake-{code}", "test", "Fake.", None, True, Scope.FILE, check)


def breaks_once_fixed(text: str) -> Edit | None:
    """Open a bracket at the start once the directive is gone."""
    return Edit(0, 0, "(") if UNUSED not in text else None


def endless(text: str) -> Edit:
    """Always add one more comment line at the end."""
    return Edit(len(text), len(text), "#\n")


def fix_of(*bounds: tuple[int, int]) -> Fix:
    return Fix(tuple(Edit(start, end, "") for start, end in bounds))


class SelectFixesTest(unittest.TestCase):
    def test_sorted_by_start(self) -> None:
        late, early = fix_of((8, 9)), fix_of((1, 2))
        self.assertEqual(select_fixes([late, early]), [early, late])

    def test_overlapping_fix_is_left_for_the_next_pass(self) -> None:
        first, overlapping, after = fix_of((0, 5)), fix_of((3, 8)), fix_of((6, 7))
        self.assertEqual(select_fixes([after, overlapping, first]), [first, after])

    def test_touching_fixes_overlap_as_in_ruff(self) -> None:
        """A fix starting where the previous one ends waits (ruff 0.17.3)."""
        self.assertEqual(
            select_fixes([fix_of((0, 5)), fix_of((5, 6))]), [fix_of((0, 5))]
        )
        self.assertEqual(
            select_fixes([fix_of((2, 2)), fix_of((2, 2))]), [fix_of((2, 2))]
        )

    def test_a_fix_spans_all_its_edits(self) -> None:
        wide, inside = fix_of((0, 1), (9, 10)), fix_of((4, 5))
        self.assertEqual(select_fixes([inside, wide]), [wide])


class ApplyEditsTest(unittest.TestCase):
    def test_indexes_refer_to_the_original_text(self) -> None:
        edits = [Edit(0, 1, "A"), Edit(4, 4, "--"), Edit(5, 6, "")]
        self.assertEqual(apply_edits("abcdefg", edits), "Abcd--eg")


class EngineTest(unittest.TestCase):
    def test_fixes_until_none_is_left(self) -> None:
        result = fix_text("# furryp: foqa:FUR102\nx = 1  # foqa:FUR102\n")
        self.assertEqual(result.text, "x = 1\n")
        self.assertEqual(
            (result.fixed, result.reverted, result.changed), (2, False, True)
        )
        self.assertEqual(result.report.diagnostics, ())

    def test_second_run_changes_nothing(self) -> None:
        first = fix_text("# furryp: foqa:FUR102\ndef f():\n    pass  # foqa:FUR102\n")
        self.assertEqual(first.text, "def f():\n    pass\n")
        second = fix_text(first.text)
        self.assertEqual(
            (second.text, second.fixed, second.changed), (first.text, 0, False)
        )

    def test_revert_to_the_previous_text_on_syntax_error(self) -> None:
        rule = fake_rule("FUR903", breaks_once_fixed)
        result = fix_text(f"x = 1{UNUSED}\n", (rule,))
        self.assertTrue(result.reverted)
        self.assertEqual((result.text, result.fixed), ("x = 1\n", 1))
        self.assertEqual([d.code for d in result.report.diagnostics], ["FUR903"])

    def test_ten_passes_at_most(self) -> None:
        rule = fake_rule("FUR904", endless)
        result = fix_text("x = 1\n", (rule,), {"select": ["FUR904"]})
        self.assertEqual(result.fixed, 10)
        self.assertEqual(result.text, "x = 1\n" + "#\n" * 10)

    def test_file_with_a_syntax_error_is_not_fixed(self) -> None:
        """As ruff: no fix is offered on a file that does not parse."""
        for text in ("x = (\n", f"x = 1 +* 2{UNUSED}\n"):
            with self.subTest(text=text):
                result = fix_text(text)
                self.assertEqual(
                    (result.text, result.fixed, result.changed), (text, 0, False)
                )
                self.assertEqual([d.fix for d in result.report.diagnostics], [None])


class WriteTest(TempDirTestCase):
    def fix_file(self, name: str, data: bytes) -> bytes:
        write_files(self.root, {name: data})
        path = self.root / name
        write_fixes(fix_path(linter_with(root=self.root), path))
        return path.read_bytes()

    def test_unchanged_file_is_not_written(self) -> None:
        write_files(self.root, {"a.py": b"x = 1\n"})
        result = fix_path(linter_with(root=self.root), self.root / "a.py")
        with mock.patch.object(Path, "write_bytes") as write_bytes:
            write_fixes(result)
        write_bytes.assert_not_called()

    def test_unreadable_file_is_not_written(self) -> None:
        result = fix_path(linter_with(root=self.root), self.root / "missing.py")
        self.assertEqual((result.original, result.changed), (None, False))
        write_fixes(result)
        self.assertFalse((self.root / "missing.py").exists())

    def test_crlf_is_kept(self) -> None:
        self.assertEqual(
            self.fix_file("a.py", b"x = 1  # foqa:FUR102\r\ny = 2\r\n"),
            b"x = 1\r\ny = 2\r\n",
        )

    def test_bom_is_kept(self) -> None:
        self.assertEqual(
            self.fix_file("a.py", b"\xef\xbb\xbfx = '\xc3\xa9'  # foqa:FUR102\n"),
            b"\xef\xbb\xbfx = '\xc3\xa9'\n",
        )

    def test_mixed_line_breaks_are_kept_outside_the_edits(self) -> None:
        self.assertEqual(
            self.fix_file("a.py", b"x = 1  # foqa:FUR102\r\ny = 2\nz = 3\r\r\n"),
            b"x = 1\r\ny = 2\nz = 3\r\r\n",
        )

    def test_latin_1_is_kept(self) -> None:
        data = b"# -*- coding: latin-1 -*-\nname = '\xe9t\xe9'  # foqa:FUR102\n"
        self.assertEqual(
            self.fix_file("a.py", data),
            b"# -*- coding: latin-1 -*-\nname = '\xe9t\xe9'\n",
        )


if __name__ == "__main__":
    unittest.main()
