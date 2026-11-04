"""Rules on fixtures, help contract (SPEC §11.0, §13) and edge cases."""

import json
import unittest

from furryp.core.diagnostic import Diagnostic
from furryp.core.registry import Rule
from furryp.lint.runner import Linter
from furryp.rules import ALL_RULES
from tests.support import (
    REPO_ROOT,
    TempDirTestCase,
    codes_at,
    lint_text,
    make_settings,
    real_registry,
    write_files,
)

FIXTURES = REPO_ROOT / "tests" / "fixtures"
FIXTURE_CONFIG = "fixture.json"
HELP_MAX = 160
FORBIDDEN_IN_HELP = ("ignore", "per-file")


def fixture_linter(rule: Rule) -> Linter:
    """Linter selecting only ``rule``, updated with the folder's ``fixture.json``."""
    data: dict[str, object] = {"select": [rule.code]}
    config = FIXTURES / rule.name / FIXTURE_CONFIG
    if config.is_file():
        data.update(json.loads(config.read_text(encoding="utf-8")))
    return Linter(real_registry(), make_settings(data), REPO_ROOT, REPO_ROOT)


def ko_diagnostics() -> list[Diagnostic]:
    """Every diagnostic produced by the ``ko_*`` fixtures."""
    found = []
    for rule in ALL_RULES:
        linter = fixture_linter(rule)
        for path in sorted((FIXTURES / rule.name).glob("ko_*.py")):
            found += linter.check_path(path.resolve()).diagnostics
    return found


class FixtureTest(unittest.TestCase):
    def test_every_rule_has_fixtures(self) -> None:
        for rule in ALL_RULES:
            with self.subTest(rule=rule.name):
                folder = FIXTURES / rule.name
                self.assertTrue(list(folder.glob("ok_*.py")))
                self.assertTrue(list(folder.glob("ko_*.py")))

    def test_ok_fixtures(self) -> None:
        for rule in ALL_RULES:
            linter = fixture_linter(rule)
            for path in sorted((FIXTURES / rule.name).glob("ok_*.py")):
                with self.subTest(fixture=f"{rule.name}/{path.name}"):
                    self.assertEqual(codes_at(linter.check_path(path.resolve())), [])

    def test_ko_fixtures(self) -> None:
        for rule in ALL_RULES:
            linter = fixture_linter(rule)
            for path in sorted((FIXTURES / rule.name).glob("ko_*.py")):
                with self.subTest(fixture=f"{rule.name}/{path.name}"):
                    expected = path.with_suffix(".expected").read_text(encoding="utf-8")
                    actual = codes_at(linter.check_path(path.resolve()))
                    self.assertEqual(actual, sorted(expected.split("\n")[:-1]))
                    self.assertTrue(all(item.endswith(rule.code) for item in actual))


class HelpContractTest(unittest.TestCase):
    def test_help_of_every_ko_diagnostic(self) -> None:
        diagnostics = ko_diagnostics()
        self.assertEqual(
            {d.code for d in diagnostics}, {rule.code for rule in ALL_RULES}
        )
        for diagnostic in diagnostics:
            with self.subTest(code=diagnostic.code, message=diagnostic.message):
                help_text = diagnostic.help
                self.assertTrue(help_text.strip())
                self.assertNotIn("\n", help_text)
                self.assertLessEqual(len(help_text), HELP_MAX)
                self.assertTrue(help_text[0].isupper(), help_text)
                for word in FORBIDDEN_IN_HELP:
                    self.assertNotIn(word, help_text.lower())
                if diagnostic.code != "FUR001":
                    self.assertNotIn("foqa", help_text.lower())


class InvalidSyntaxTest(TempDirTestCase):
    def test_messages_and_helps(self) -> None:
        write_files(self.root, {"bad.py": b'x = "\xe9"\n', "syntax.py": "x = (1,\n"})
        linter = Linter(real_registry(), make_settings(), self.root, self.root)
        cases = [
            (
                "missing.py",
                "Failed to read file: No such file or directory",
                "Check that the path exists and is readable",
            ),
            (
                "bad.py",
                "Failed to decode file: invalid or missing encoding declaration",
                (
                    "Save the file as UTF-8, or declare its encoding with a "
                    "`# -*- coding: … -*-` line"
                ),
            ),
            (
                "syntax.py",
                "SyntaxError: '(' was never closed",
                "Fix the syntax error; other checks are skipped for this file",
            ),
        ]
        for name, message, help_text in cases:
            with self.subTest(name=name):
                report = linter.check_path(self.root / name)
                found = [
                    (d.message, d.help)
                    for d in report.diagnostics
                    if d.code == "FUR000"
                ]
                self.assertEqual(found, [(message, help_text)])

    def test_unreadable_files_have_no_lines(self) -> None:
        linter = Linter(real_registry(), make_settings(), self.root, self.root)
        report = linter.check_path(self.root / "missing.py")
        self.assertIsNone(report.lines)
        self.assertEqual(codes_at(report), ["1:1 FUR000"])

    def test_only_textual_rules_run_on_invalid_syntax(self) -> None:
        settings = make_settings({"rules": {"file-too-long": {"max-lines": 0}}})
        report = lint_text("x = (  # foqa:FUR999\n", settings)
        self.assertEqual(codes_at(report), ["1:1 FUR102", "1:5 FUR000"])


class FileTooLongTest(unittest.TestCase):
    def test_default_limit(self) -> None:
        settings = make_settings({"select": ["FUR102"]})
        self.assertEqual(codes_at(lint_text("x = 1\n" * 1000, settings)), [])
        report = lint_text("x = 1\n" * 1000 + "y = 22\n", settings)
        self.assertEqual(codes_at(report), ["1001:1 FUR102"])
        diagnostic = report.diagnostics[0]
        self.assertEqual(diagnostic.message, "File has too many lines (1001 > 1000)")
        self.assertEqual(
            diagnostic.help,
            "Long files are hard to navigate; consider splitting this one into smaller modules",
        )
        self.assertEqual(
            (diagnostic.span.end.line, diagnostic.span.end.column), (1001, 7)
        )

    def test_physical_lines(self) -> None:
        settings = make_settings(
            {"select": ["FUR102"], "rules": {"file-too-long": {"max-lines": 2}}}
        )
        self.assertEqual(codes_at(lint_text("x = 1\r\ny = '\f\v'\n", settings)), [])
        self.assertEqual(
            codes_at(lint_text("x = 1\ry = 2\rz = 3", settings)), ["3:1 FUR102"]
        )


if __name__ == "__main__":
    unittest.main()
