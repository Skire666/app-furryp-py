"""``foqa`` directives: detection and suppression (SPEC §6)."""

import unittest
from pathlib import Path

from furryp.core.diagnostic import line_span
from furryp.core.source import parse_source
from furryp.core.suppression import DirectiveKind, find_directives, scan_directives
from tests.support import FLAGGED, codes_at, lint_text, make_settings, real_registry

CHAIN_ONLY = {"select": ["FUR403"]}
EXPECTED_COLON = (
    "expected `:` followed by a comma-separated list of codes"
    " (e.g., `# foqa:FUR101,FUR403`)."
)
EXPECTED_LIST = (
    "expected a comma-separated list of codes (e.g., `# foqa:FUR101,FUR403`)."
)
EXPECTED_CODE = (
    "expected code to consist of uppercase letters followed by digits only"
    " (e.g. `FUR101`)"
)
MISSING_CODE = (
    "Missing or joined rule code(s) at a.py:1: expected rule code between commas"
)
JOINED_CODES = (
    "Missing or joined rule code(s) at a.py:1:"
    " expected comma or space delimiter between codes"
)
FILE_TOO_LONG_AT_LINE_1 = {
    "select": ["FUR102"],
    "rules": {"file-too-long": {"max-lines": 0}},
}


def directives(text: str) -> list[tuple[DirectiveKind, tuple[str, ...], int, int]]:
    source = parse_source(Path("a.py"), "a.py", text, "utf-8")
    return [
        (item.kind, item.identifiers, item.first_line, item.last_line)
        for item in find_directives(source, real_registry())
    ]


def warnings(text: str) -> list[str]:
    source = parse_source(Path("a.py"), "a.py", text, "utf-8")
    return list(scan_directives(source, real_registry()).warnings)


def chain_codes(text: str) -> list[str]:
    """Diagnostics of ``text`` with only FUR403 selected."""
    return codes_at(lint_text(text, make_settings(CHAIN_ONLY)))


class DirectiveDetectionTest(unittest.TestCase):
    def test_line_directive(self) -> None:
        self.assertEqual(
            directives("x = 1  # foqa:FUR101, function-too-long ,FUR403\n"),
            [(DirectiveKind.LINE, ("FUR101", "function-too-long", "FUR403"), 1, 1)],
        )

    def test_blanket_and_case(self) -> None:
        self.assertEqual(
            directives("x = 1  # FOQA\ny = 2  # Foqa: FUR101\n"),
            [(DirectiveKind.LINE, (), 1, 1), (DirectiveKind.LINE, ("FUR101",), 2, 2)],
        )

    def test_file_directive(self) -> None:
        self.assertEqual(
            directives("# furryp: foqa\n    # furryp: FOQA:FUR102,FUR201\n"),
            [
                (DirectiveKind.FILE, (), 1, 1),
                (DirectiveKind.FILE, ("FUR102", "FUR201"), 2, 2),
            ],
        )

    def test_file_directive_must_be_alone_on_its_line(self) -> None:
        self.assertEqual(directives("x = 1  # furryp: foqa:FUR102\n"), [])

    def test_after_another_comment_and_with_noqa(self) -> None:
        for comment in (
            "# reason  # foqa:FUR403",
            "# noqa: E501  # foqa:FUR403",
            "# foqa:FUR403  # noqa: E501",
        ):
            with self.subTest(comment=comment):
                self.assertEqual(
                    directives(f"x = 1  {comment}\n"),
                    [(DirectiveKind.LINE, ("FUR403",), 1, 1)],
                )

    def test_strings_are_not_comments(self) -> None:
        self.assertEqual(directives('x = "# foqa:FUR403"\ny = """\n# foqa\n"""\n'), [])

    def test_forms_read_like_noqa(self) -> None:
        # Each form behaves like its `# noqa` twin in ruff 0.17.3 (checked).
        for comment, identifiers in (
            ("# foqa bar", ()),
            ("# foqa - reason", ()),
            ("# foqa (reason)", ()),
            ("# foqa FUR101", ()),
            ("# foqa\tFUR101", ()),
            ("# foqa#foo", ()),
            ("# foo # foqa bar", ()),
            ("#foqa", ()),
            ("# foqa : FUR101", ("FUR101",)),
            ("# foqa  :  FUR101", ("FUR101",)),
            ("# foqa: FUR101 FUR102", ("FUR101", "FUR102")),
            ("# foqa: FUR101 FUR102 bar", ("FUR101", "FUR102")),
            ("# foqa: FUR101 bar", ("FUR101",)),
            ("# foqa: FUR101 Reason", ("FUR101",)),
            ("# foqa: FUR101 TODO: fix", ("FUR101",)),
            ("# foqa: FUR101 AB-1", ("FUR101",)),
            ("# foqa: FUR101 - reason", ("FUR101",)),
            ("# foqa: FUR101 (reason)", ("FUR101",)),
            ("# foqa: FUR101#foo", ("FUR101",)),
            ("# foqa: FUR101 # bar", ("FUR101",)),
            ("# foqa: FUR101,", ("FUR101",)),
            ("# foqa: FUR101, ", ("FUR101",)),
            ("# foqa:,FUR101", ("FUR101",)),
            ("# foqa: FUR101,,FUR102", ("FUR101", "FUR102")),
            ("# foqa: FUR101 , FUR102", ("FUR101", "FUR102")),
            ("# foqa: FUR101 # foqa: FUR102", ("FUR101",)),
            ("# foqa: FUR101 # foqa.", ("FUR101",)),
            ("# foqa: FUR101FUR102", ("FUR101", "FUR102")),
            ("# foqa: E5", ("E5",)),
            ("# foqa: FUR101, reason", ("FUR101",)),
            ("# foqa: FUR101,bar,FUR102", ("FUR101",)),
            ("# foqa: FUR101,fur102", ("FUR101",)),
        ):
            with self.subTest(comment=comment):
                self.assertEqual(
                    directives(f"x = 1  {comment}\n"),
                    [(DirectiveKind.LINE, identifiers, 1, 1)],
                )

    def test_invalid_forms_are_not_directives(self) -> None:
        # A word or a sign stuck to it: ruff warns and the directive does nothing.
        for comment in (
            "# lines carrying a bare `# foqa`",
            "# see `# foqa:FUR101` here",
            "# foo (# foqa)",
            "# foo # foqa.",
            "# foqa`",
            "# foqa: FUR101`",
            "# foqa: FUR101;",
            "# foqa: FUR101:",
            "# foqa: FUR101: reason",
            "# foqa: FUR101 FUR102bar",
            "# foqa: FUR101 FUR102-bar",
            "# foqa: FUR101 A1b",
            "# foqa: FUR101 FUR102 A1b",
            "# foqa-foo",
            "# foqa_foo",
            "# foqafoo",
            "# foqa, FUR101",
            "# foqa; FUR101",
            "# foqa:",
            "# foqa: ",
            "# foqa :",
            "# foqa:#foo",
            "# foqa: # foo",
            "# foqa: ,",
            "# foqa: bad-name",
            "# foqa: bad-name, FUR101",
            "# foqa: fur101",
            "# foqa: 501",
            "# foqa: FUR",
            "# foqa: Fx1",
            "# foqa: FUR101E",
            "# foqa: function-too-long;",
            "# foofoqa",
            "# see the foqa directive",
        ):
            with self.subTest(comment=comment):
                self.assertEqual(directives(f"x = 1  {comment}\n"), [])

    def test_only_the_first_keyword_counts(self) -> None:
        # As ruff 0.17.3, which stops there even if the directive is invalid.
        for comment in (
            "# foqa. # foqa:FUR101",
            "# foo `# foqa`  # foqa:FUR101",
            "# foqafoo # foqa:FUR101",
        ):
            with self.subTest(comment=comment):
                self.assertEqual(directives(f"x = 1  {comment}\n"), [])

    def test_rule_names_are_identifiers(self) -> None:
        # furryp only (SPEC §4.5): a known name is read like a code.
        for comment, identifiers in (
            ("# foqa:function-too-long", ("function-too-long",)),
            ("# foqa:FUR102,function-too-long", ("FUR102", "function-too-long")),
            ("# foqa:FUR102 function-too-long", ("FUR102", "function-too-long")),
            ("# foqa:function-too-long FUR102", ("function-too-long", "FUR102")),
            ("# foqa:function-too-long reason", ("function-too-long",)),
        ):
            with self.subTest(comment=comment):
                self.assertEqual(
                    directives(f"x = 1  {comment}\n"),
                    [(DirectiveKind.LINE, identifiers, 1, 1)],
                )

    def test_file_forms_read_like_noqa(self) -> None:
        for comment, identifiers in (
            ("#furryp:foqa", ()),
            ("# furryp : foqa", ()),
            ("# furryp: foqa bar", ()),
            ("# furryp: foqa FUR102", ()),
            ("# furryp: foqa: FUR102 bar", ("FUR102",)),
            ("# furryp: foqa: FUR102 FUR201", ("FUR102", "FUR201")),
            ("# foo # furryp: foqa", ()),
            ("# foo # furryp: foqa: FUR102", ("FUR102",)),
            ("# furryp: foqa: FUR102 # foqa.", ("FUR102",)),
        ):
            with self.subTest(comment=comment):
                self.assertEqual(
                    directives(f"{comment}\n"),
                    [(DirectiveKind.FILE, identifiers, 1, 1)],
                )

    def test_invalid_file_forms_are_not_directives(self) -> None:
        for comment in (
            "# furryp: foqa.",
            "# furryp: foqa`",
            "# furryp: foqa: FUR102`",
            "# furryp: foqa:",
            "# FURRYP: foqa",
        ):
            with self.subTest(comment=comment):
                self.assertEqual(directives(f"{comment}\n"), [])

    def test_a_form_really_suppresses_or_not(self) -> None:
        # The effect on a diagnostic, not only the reading of the comment.
        for comment, remaining in (
            ("# foqa bar", []),
            ("# foqa: FUR403 bar", []),
            ("# foqa: FUR102 FUR403", []),
            ("# foqa`", ["1:5 FUR403"]),
            ("# foqa: FUR403;", ["1:5 FUR403"]),
            ("# foqa:", ["1:5 FUR403"]),
            ("# foqa. # foqa:FUR403", ["1:5 FUR403"]),
            ("# foqa:FUR102 # foqa:FUR403", ["1:5 FUR403"]),
            ("# foqa:FUR403,bar,FUR102", []),
        ):
            with self.subTest(comment=comment):
                self.assertEqual(chain_codes(f"{FLAGGED}  {comment}\n"), remaining)

    def test_logical_line(self) -> None:
        text = "def f(\n    a,\n):  # foqa:FUR102\n    pass\n# foqa\n"
        self.assertEqual(
            directives(text),
            [(DirectiveKind.LINE, ("FUR102",), 1, 3), (DirectiveKind.LINE, (), 5, 5)],
        )

    def test_span_covers_the_directive(self) -> None:
        source = parse_source(
            Path("a.py"), "a.py", "x = 1  # why  # foqa:FUR403\n", "utf-8"
        )
        found = find_directives(source, real_registry())
        self.assertEqual(found[0].span, line_span(1, 15, 28))


class DirectiveWarningTest(unittest.TestCase):
    """The warnings of ruff 0.17.3, with ``foqa`` for ``noqa`` (checked)."""

    def test_invalid_line_directive(self) -> None:
        location = "Invalid `# foqa` directive on a.py:1: "
        for comment, reason in (
            ("# foqa.", EXPECTED_COLON),
            ("# foqa`", EXPECTED_COLON),
            ("# foqafoo", EXPECTED_COLON),
            ("# foo (# foqa)", EXPECTED_COLON),
            ("# foqa, FUR101", EXPECTED_COLON),
            ("# foqa. # foqa:FUR403", EXPECTED_COLON),
            ("# foqa:", EXPECTED_LIST),
            ("# foqa :", EXPECTED_LIST),
            ("# foqa:#foo", EXPECTED_LIST),
            ("# foqa: ,", EXPECTED_LIST),
            ("# foqa: bad-name", EXPECTED_LIST),
            ("# foqa: fur101", EXPECTED_LIST),
            ("# foqa: FUR101;", EXPECTED_CODE),
            ("# foqa: FUR101:", EXPECTED_CODE),
            ("# foqa: FUR101x", EXPECTED_CODE),
            ("# foqa: FUR101E", EXPECTED_CODE),
            ("# foqa: FUR101 FUR102bar", EXPECTED_CODE),
        ):
            with self.subTest(comment=comment):
                self.assertEqual(warnings(f"x = 1  {comment}\n"), [location + reason])

    def test_invalid_file_directive(self) -> None:
        location = "Invalid `# furryp: foqa` directive at a.py:1: "
        for comment, reason in (
            ("# furryp: foqa.", EXPECTED_COLON),
            ("# furryp: foqa:", EXPECTED_LIST),
            ("# furryp: foqa: bad-name", EXPECTED_LIST),
            ("# furryp: foqa: FUR102`", EXPECTED_CODE),
        ):
            with self.subTest(comment=comment):
                self.assertEqual(warnings(f"{comment}\n"), [location + reason])

    def test_list_problems_keep_the_directive(self) -> None:
        for comment, problems, identifiers in (
            ("# foqa: FUR101,,FUR102", [MISSING_CODE], ("FUR101", "FUR102")),
            ("# foqa: FUR101 , FUR102", [MISSING_CODE], ("FUR101", "FUR102")),
            ("# foqa: FUR101, ,FUR102", [MISSING_CODE], ("FUR101", "FUR102")),
            ("# foqa:,FUR101", [MISSING_CODE], ("FUR101",)),
            ("# foqa: FUR101,,", [MISSING_CODE], ("FUR101",)),
            ("# foqa: FUR101 ,#foo", [MISSING_CODE], ("FUR101",)),
            (
                "# foqa: FUR101 ,, FUR102",
                [MISSING_CODE, MISSING_CODE],
                ("FUR101", "FUR102"),
            ),
            ("# foqa: FUR101FUR102", [JOINED_CODES], ("FUR101", "FUR102")),
        ):
            with self.subTest(comment=comment):
                text = f"x = 1  {comment}\n"
                self.assertEqual(warnings(text), problems)
                self.assertEqual(
                    directives(text), [(DirectiveKind.LINE, identifiers, 1, 1)]
                )

    def test_file_directive_list_problems(self) -> None:
        self.assertEqual(warnings("# furryp: foqa: FUR102,,FUR201\n"), [MISSING_CODE])
        self.assertEqual(warnings("# furryp: foqa: FUR102FUR201\n"), [JOINED_CODES])

    def test_file_directive_after_code(self) -> None:
        expected = [
            "Unexpected `# furryp: foqa` directive at a.py:1. File-level suppression"
            " comments must appear on their own line. For line-level suppression, omit"
            " the `furryp:` prefix."
        ]
        for comment in ("# furryp: foqa", "# furryp: foqa:FUR102"):
            with self.subTest(comment=comment):
                text = f"x = 1  {comment}\n"
                self.assertEqual(warnings(text), expected)
                self.assertEqual(directives(text), [])
        self.assertEqual(
            warnings("x = 1  # furryp: foqa.\n"),
            [f"Invalid `# furryp: foqa` directive at a.py:1: {EXPECTED_COLON}"],
        )

    def test_silent_forms(self) -> None:
        for text in (
            "x = 1  # foqa\n",
            "x = 1  # foqa bar\n",
            "x = 1  # foqa: FUR101, FUR102\n",
            "x = 1  # foqa: FUR101,\n",
            "x = 1  # foqa: FUR101, \n",
            "x = 1  # foqa: FUR101, #foo\n",
            "x = 1  # foqa: FUR999\n",
            "x = 1  # foqa: FUR101 reason\n",
            "x = 1  # foofoqa\n",
            "x = 1  # see the foqa directive\n",
            'x = "# foqa."\n',
            "# FURRYP: FOQA: FUR102\n",
        ):
            with self.subTest(text=text):
                self.assertEqual(warnings(text), [])

    def test_file_forms_come_first(self) -> None:
        # As ruff prints them: `x = 1  # noqa.`, then `# ruff: noqa.`, line 2 first.
        self.assertEqual(
            warnings("x = 1  # foqa.\n# furryp: foqa.\n"),
            [
                f"Invalid `# furryp: foqa` directive at a.py:2: {EXPECTED_COLON}",
                f"Invalid `# foqa` directive on a.py:1: {EXPECTED_COLON}",
            ],
        )

    def test_each_comment_is_read_on_its_own(self) -> None:
        self.assertEqual(
            directives("# furryp: foqa.\n# furryp: foqa: FUR102\n"),
            [(DirectiveKind.FILE, ("FUR102",), 2, 2)],
        )

    def test_both_forms_in_one_comment(self) -> None:
        # As ruff: two parsers, so an invalid file form does not hide the line form.
        self.assertEqual(
            directives("# furryp: foqa. # foqa: FUR102\n"),
            [(DirectiveKind.LINE, ("FUR102",), 1, 1)],
        )
        self.assertEqual(
            directives("# furryp: foqa: FUR102 # foqa: FUR101\n"),
            [
                (DirectiveKind.FILE, ("FUR102",), 1, 1),
                (DirectiveKind.LINE, ("FUR101",), 1, 1),
            ],
        )


class SuppressionTest(unittest.TestCase):
    def test_line_directive_by_code_or_name(self) -> None:
        self.assertEqual(chain_codes(f"{FLAGGED}\n"), ["1:5 FUR403"])
        for comment in (
            "# foqa:FUR403",
            "# foqa:demeter-chain",
            "# foqa",
            "# FOQA: FUR102, FUR403",
        ):
            with self.subTest(comment=comment):
                report = lint_text(f"{FLAGGED}  {comment}\n", make_settings(CHAIN_ONLY))
                self.assertEqual(codes_at(report), [])
                self.assertEqual([d.code for d in report.suppressed], ["FUR403"])

    def test_other_rule_does_not_suppress(self) -> None:
        self.assertEqual(chain_codes(f"{FLAGGED}  # foqa:FUR102\n"), ["1:5 FUR403"])

    def test_a_file_directive_comes_before_a_line_directive(self) -> None:
        settings = make_settings(CHAIN_ONLY)
        report = lint_text(
            f"# furryp: foqa:FUR403\n{FLAGGED}  # foqa:FUR403\n", settings
        )
        self.assertEqual(codes_at(report), [])
        self.assertEqual([d.code for d in report.suppressed], ["FUR403"])

    def test_string_does_not_suppress(self) -> None:
        self.assertEqual(
            chain_codes('x = a.b.c.d.e("# foqa:FUR403")\n'), ["1:5 FUR403"]
        )

    def test_file_directive(self) -> None:
        for directive in (
            "# furryp: foqa",
            "# furryp: foqa:FUR403",
            "# furryp: foqa:demeter-chain",
        ):
            with self.subTest(directive=directive):
                self.assertEqual(chain_codes(f"{directive}\n\n{FLAGGED}\n"), [])

    def test_directive_on_last_line_of_a_folded_statement(self) -> None:
        text = "def f(\n    a,\n):  # foqa:FUR102\n    return a\n"
        settings = make_settings(FILE_TOO_LONG_AT_LINE_1)
        self.assertEqual(
            codes_at(lint_text(text.replace("  # foqa:FUR102", ""), settings)),
            ["1:1 FUR102"],
        )
        report = lint_text(text, settings)
        self.assertEqual(codes_at(report), [])
        self.assertEqual([d.span.start.line for d in report.suppressed], [1])

    def test_directive_on_any_line_of_a_multi_line_statement(self) -> None:
        settings = make_settings(
            {
                "select": ["FUR102", "FUR001"],
                "rules": {"file-too-long": {"max-lines": 2}},
            }
        )
        lines = ["x = max(", "    1,", ")"]
        self.assertEqual(
            codes_at(lint_text("\n".join(lines) + "\n", settings)), ["3:1 FUR102"]
        )
        for index in range(len(lines)):
            with self.subTest(line=index + 1):
                commented = list(lines)
                commented[index] += "  # foqa:FUR102"
                report = lint_text("\n".join(commented) + "\n", settings)
                self.assertEqual(codes_at(report), [])
                self.assertEqual([d.span.start.line for d in report.suppressed], [3])

    def test_comment_alone_covers_its_line_only(self) -> None:
        settings = make_settings(FILE_TOO_LONG_AT_LINE_1)
        report = lint_text("x = 1\n# foqa:FUR102\n", settings)
        self.assertEqual(codes_at(report), ["1:1 FUR102"])

    def test_invalid_syntax_is_never_suppressed(self) -> None:
        report = lint_text(
            "# furryp: foqa\nx = (\n", make_settings({"select": ["FUR000"]})
        )
        self.assertEqual(codes_at(report), ["2:5 FUR000"])
        report = lint_text(
            "x = (  # foqa:FUR000\n", make_settings({"select": ["FUR000"]})
        )
        self.assertEqual(codes_at(report), ["1:5 FUR000"])

    def test_invalid_syntax_is_not_suppressed_when_directives_are_read(self) -> None:
        # This code tokenizes, unlike `x = (`: its directives are really read.
        settings = make_settings({"select": ["FUR000"]})
        for text, expected in (
            ("x = 1 +* 2  # foqa:FUR000\n", ["1:8 FUR000"]),
            ("x = 1 +* 2  # foqa:invalid-syntax\n", ["1:8 FUR000"]),
            ("x = 1 +* 2  # foqa\n", ["1:8 FUR000"]),
            ("# furryp: foqa\nx = 1 +* 2\n", ["2:8 FUR000"]),
            ("# furryp: foqa:FUR000\nx = 1 +* 2\n", ["2:8 FUR000"]),
        ):
            with self.subTest(text=text):
                report = lint_text(text, settings)
                self.assertEqual(codes_at(report), expected)
                self.assertEqual(report.suppressed, ())

    def test_textual_rules_on_invalid_syntax(self) -> None:
        settings = make_settings(FILE_TOO_LONG_AT_LINE_1)
        report = lint_text("# furryp: foqa:FUR102\nx = 1 +* 2\n", settings)
        self.assertEqual(codes_at(report), ["2:8 FUR000"])
        report = lint_text("# furryp: foqa:FUR102\nx = (\n", settings)
        self.assertEqual(codes_at(report), ["1:1 FUR102", "2:5 FUR000"])


if __name__ == "__main__":
    unittest.main()
