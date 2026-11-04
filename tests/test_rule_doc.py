"""Rule documentation shown by ``furryp rule`` (SPEC §4.6, §13)."""

import json
import re
import unittest

from furryp.core.registry import Rule, Scope
from furryp.fix.engine import fix_report
from furryp.output.rule_doc import read_rule_doc, render_rule
from furryp.rules import ALL_RULES
from tests.support import (
    CONFIG,
    PYPROJECT,
    TempDirTestCase,
    lint_text,
    linter_with,
    make_settings,
    run_furryp,
    text_source,
    write_files,
)

WRITTEN_SECTIONS = (
    "## What it measures",
    "## Why it matters",
    "## How to fix it well",
    "## What not to do",
    "## Example",
)
RENDERED_SECTIONS = (
    "## What it measures",
    "## Why it matters",
    "## Options",
    "## How to fix it well",
    "## What not to do",
    "## Example",
)
CODE_BLOCK = re.compile(
    r"^```(?P<language>\w+)\n(?P<code>.*?)^```$", re.MULTILINE | re.DOTALL
)

# The table of SPEC §11.0, with its categories in English.
CATALOGUE = {
    "FUR000": ("invalid-syntax", "errors", Scope.FILE, False),
    "FUR001": ("unused-foqa", "suppressions", Scope.LINE, True),
    "FUR101": ("function-too-long", "size", Scope.LINE, False),
    "FUR102": ("file-too-long", "size", Scope.FILE, False),
    "FUR201": ("halstead-file", "halstead", Scope.FILE, False),
    "FUR202": ("halstead-function", "halstead", Scope.LINE, False),
    "FUR203": ("cognitive-complexity", "complexity", Scope.LINE, False),
    "FUR401": ("too-complex-class", "design", Scope.LINE, False),
    "FUR402": ("layer-violation", "design", Scope.LINE, False),
    "FUR403": ("demeter-chain", "design", Scope.LINE, False),
    "FUR404": ("too-many-instance-attributes", "design", Scope.LINE, False),
}


def heading_positions(text: str, headings: tuple[str, ...]) -> list[int]:
    lines = text.split("\n")
    return [
        next(index for index, line in enumerate(lines) if line.startswith(heading))
        for heading in headings
    ]


def example(rule: Rule) -> tuple[dict[str, object], str, str]:
    """Configuration (optional ```json block, as in ``furryp.json``), flagged
    and fixed code of the example of a rule."""
    section = read_rule_doc(rule.code).partition("## Example")[2]
    blocks = [
        (match["language"], match["code"]) for match in CODE_BLOCK.finditer(section)
    ]
    data = json.loads(blocks.pop(0)[1]) if blocks[0][0] == "json" else {}
    (flagged_language, flagged), (fixed_language, fixed) = blocks
    assert flagged_language == fixed_language == "python", rule.code
    return data, flagged, fixed


class RuleDocTest(unittest.TestCase):
    def test_catalogue(self) -> None:
        self.assertEqual(
            {
                rule.code: (rule.name, rule.category, rule.scope, rule.fixable)
                for rule in ALL_RULES
            },
            CATALOGUE,
        )

    def test_header_of_a_rendered_rule(self) -> None:
        rule = next(rule for rule in ALL_RULES if rule.code == "FUR203")
        self.assertTrue(
            render_rule(rule, make_settings()).startswith(
                "# cognitive-complexity (FUR203)\n\n"
                "Category: complexity · Scope: line · Fix: not available\n\n"
            )
        )

    def test_written_sections(self) -> None:
        for rule in ALL_RULES:
            with self.subTest(rule=rule.code):
                text = read_rule_doc(rule.code)
                positions = heading_positions(text, WRITTEN_SECTIONS)
                self.assertEqual(positions, sorted(positions))
                self.assertNotIn("## Options", text)

    def test_rendered_documentation(self) -> None:
        for rule in ALL_RULES:
            with self.subTest(rule=rule.code):
                text = render_rule(rule, make_settings())
                fix = "available" if rule.fixable else "not available"
                header = (
                    f"# {rule.name} ({rule.code})\n\n"
                    f"Category: {rule.category} · Scope: {rule.scope} · Fix: {fix}\n\n"
                )
                self.assertTrue(text.startswith(header), text[:200])
                positions = heading_positions(text, RENDERED_SECTIONS)
                self.assertEqual(positions, sorted(positions))

    def test_examples(self) -> None:
        for rule in ALL_RULES:
            with self.subTest(rule=rule.code):
                data, flagged, fixed = example(rule)
                settings = make_settings(data)
                flagged_codes = {
                    d.code for d in lint_text(flagged, settings).diagnostics
                }
                fixed_codes = {d.code for d in lint_text(fixed, settings).diagnostics}
                self.assertIn(rule.code, flagged_codes)
                self.assertNotIn(rule.code, fixed_codes)

    def test_fix_turns_the_flagged_example_into_the_fixed_one(self) -> None:
        """For a fixable rule, selected alone, ``--fix`` gives the fixed code."""
        for rule in ALL_RULES:
            if not rule.fixable:
                continue
            with self.subTest(rule=rule.code):
                data, flagged, fixed = example(rule)
                linter = linter_with(data={**data, "select": [rule.code]})
                result = fix_report(linter, linter.check_source(text_source(flagged)))
                self.assertEqual(result.text, fixed)

    def test_options(self) -> None:
        by_code = {rule.code: rule for rule in ALL_RULES}
        settings = make_settings({"rules": {"file-too-long": {"max-lines": 30}}})
        self.assertIn(
            "## Options (furryp.json → rules.file-too-long)\n\n"
            "- max-lines = 30 (default: 1000)\n\n## How to fix it well",
            render_rule(by_code["FUR102"], settings),
        )
        self.assertIn(
            '- ignore-roots = ["self", "cls"] (default: ["self", "cls"])\n',
            render_rule(by_code["FUR403"], settings),
        )
        for code in ("FUR000", "FUR001"):
            with self.subTest(code=code):
                self.assertIn(
                    "## Options\n\nThis rule has no options.\n\n## How to fix it well",
                    render_rule(by_code[code], settings),
                )


class RuleCommandTest(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        write_files(
            self.root,
            {PYPROJECT: "", CONFIG: '{"rules": {"file-too-long": {"max-lines": 30}}}'},
        )

    def test_code_and_name(self) -> None:
        for identifier in ("FUR102", "file-too-long"):
            with self.subTest(identifier=identifier):
                result = run_furryp(["rule", identifier], self.root)
                self.assertEqual((result.returncode, result.stderr), (0, ""))
                self.assertTrue(result.stdout.startswith("# file-too-long (FUR102)\n"))
                self.assertIn("- max-lines = 30 (default: 1000)\n", result.stdout)

    def test_explicit_config(self) -> None:
        write_files(
            self.root, {"other.json": '{"rules": {"file-too-long": {"max-lines": 7}}}'}
        )
        result = run_furryp(["rule", "FUR102", "--config", "other.json"], self.root)
        self.assertIn("- max-lines = 7 (default: 1000)\n", result.stdout)

    def test_all(self) -> None:
        result = run_furryp(["rule", "--all"], self.root)
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        documents = result.stdout.split("\n\n---\n\n")
        self.assertEqual(len(documents), len(ALL_RULES))
        titles = [document.split("\n", 1)[0] for document in documents]
        self.assertEqual(
            titles,
            [f"# {r.name} ({r.code})" for r in sorted(ALL_RULES, key=lambda r: r.code)],
        )

    def test_unknown_rule(self) -> None:
        result = run_furryp(["rule", "demeter"], self.root)
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertEqual(
            result.stderr,
            'error: unknown rule "demeter" (did you mean "demeter-chain"?)\n',
        )

    def test_invalid_configuration(self) -> None:
        write_files(self.root, {CONFIG: '{"rules": {"invalid-syntax": {}}}'})
        result = run_furryp(["rule", "FUR000"], self.root)
        self.assertEqual(
            (result.returncode, result.stderr),
            (2, "error: furryp.json: rules.invalid-syntax: rule has no options\n"),
        )


if __name__ == "__main__":
    unittest.main()
