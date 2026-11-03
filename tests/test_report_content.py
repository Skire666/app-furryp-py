"""What each section and each column of the report really shows (SPEC §12.3).

The other tests of the report look at the model, or at the whole page: here each
value is read in its section, under its own label.
"""

import colorsys
import platform
import re
import unittest
from pathlib import Path

import furryp
from furryp.core.errors import FileFailure
from furryp.metrics.halstead import Halstead
from furryp.report.render import render_report
from tests.report_support import (
    TIMING,
    cards_of,
    class_measures,
    failed,
    function,
    model_of,
    rating_cards_of,
    rows_of,
    section_of,
    summary,
    tables_of,
)
from tests.support import REPO_ROOT

STYLE_SHEET = REPO_ROOT / "furryp" / "report" / "templates" / "report.css"
TEMPLATES = STYLE_SHEET.parent
CATEGORY_RULES = {
    "size": ["FUR101", "FUR102"],
    "complexity": ["FUR203"],
    "halstead": ["FUR201", "FUR202"],
    "design": ["FUR401", "FUR402", "FUR403", "FUR404"],
}
RULE_COLUMNS = ["Code", "Name", "Violations", "Files", "Suppressed", "Fixable"]
FILE_MEASURES = Halstead(10, 20, 300, 400)
FUNCTION_MEASURES = Halstead(4, 5, 6, 7)


def number(value: float) -> str:
    """Return a real as the report shows it."""
    return f"{value:,.2f}"


def worst_rows(text: str, key: str) -> list[dict[str, str]]:
    """Return the rows of the table of worst files of a category: its last table."""
    return rows_of(tables_of(section_of(text, key))[-1])


def measures(text: str, key: str) -> dict[str, dict[str, str]]:
    """Return the rows of the table of measures of a category, by label."""
    table = tables_of(section_of(text, key))[0]
    return {row[table[0][0]]: row for row in rows_of(table)}


def rule_rows(text: str, key: str) -> list[dict[str, str]]:
    """Return the rows of the table of the violations per rule of a category."""
    return rows_of(tables_of(section_of(text, key))[1])


def one_file_report() -> str:
    """Return a report of one file whose values are all different."""
    violations = {"FUR101": 1, "FUR203": 2, "FUR202": 1}
    file = summary(
        "big.py",
        lines=1001,
        code_lines=702,
        functions=[
            function("long_one", code_lines=41, cognitive=31),
            function("short", code_lines=5, cognitive=3),
        ],
        classes=[
            class_measures("K", complexity=77, attributes=3),
            class_measures("L", complexity=5, attributes=19),
        ],
        halstead=FILE_MEASURES,
        violations={**violations, "FUR402": 4, "FUR403": 5, "FUR401": 6},
        suppressed={"FUR101": 7},
        fixable={"FUR403": 1},
    )
    return render_report(model_of([file]))


class WorstFilesColumnsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = one_file_report()

    def test_size(self) -> None:
        self.assertEqual(
            worst_rows(self.text, "size"),
            [
                {
                    "File": "big.py",
                    "Lines": "1,001",
                    "Lines of code": "702",
                    "Functions": "2",
                    "Longest function": "long_one (41)",
                }
            ],
        )

    def test_complexity(self) -> None:
        self.assertEqual(
            worst_rows(self.text, "complexity"),
            [
                {
                    "File": "big.py",
                    "Total complexity": "34",
                    "Max complexity": "31",
                    "Most complex function": "long_one (31)",
                }
            ],
        )

    def test_halstead(self) -> None:
        self.assertEqual(
            worst_rows(self.text, "halstead"),
            [
                {
                    "File": "big.py",
                    "Volume": number(FILE_MEASURES.volume),
                    "Difficulty": number(FILE_MEASURES.difficulty),
                    "Effort": number(FILE_MEASURES.effort),
                    "Bugs": number(FILE_MEASURES.bugs),
                }
            ],
        )

    def test_design(self) -> None:
        self.assertEqual(
            worst_rows(self.text, "design"),
            [
                {
                    "File": "big.py",
                    "Violations": "15",
                    "Max class complexity": "77",
                    "Max attributes": "19",
                    "Contracts": "4",
                    "Chains": "5",
                }
            ],
        )


class MeasuresTablesTest(unittest.TestCase):
    """Three files of 1, 2 and 9 units: mean, median, max and total all differ."""

    def setUp(self) -> None:
        self.files = [
            summary(
                f"{value}.py",
                lines=value,
                code_lines=value * 10,
                functions=[
                    function(
                        code_lines=value * 100,
                        cognitive=value * 1000,
                        halstead=Halstead(value + 1, value + 1, value, value),
                    )
                ],
                classes=[class_measures(complexity=value, attributes=value * 2)],
                halstead=Halstead(value + 3, value + 3, value * 5, value * 5),
            )
            for value in (1, 2, 9)
        ]
        self.text = render_report(model_of(self.files))

    def test_size(self) -> None:
        rows = measures(self.text, "size")
        self.assertEqual(
            rows["Lines per file"],
            {
                "Measure": "Lines per file",
                "Mean": "4.00",
                "Median": "2.00",
                "Max": "9",
                "Total": "12",
            },
        )
        self.assertEqual(rows["Lines of code per file"]["Total"], "120")
        self.assertEqual(rows["Lines of code per function"]["Max"], "900")
        self.assertEqual(rows["Functions over 25 lines of code"]["Total"], "3")

    def test_complexity(self) -> None:
        rows = measures(self.text, "complexity")
        row = next(value for key, value in rows.items() if key.startswith("Cognitive"))
        self.assertEqual(
            (row["Mean"], row["Median"], row["Max"], row["Total"]),
            ("4,000.00", "2,000.00", "9,000", "12,000"),
        )
        self.assertEqual(rows["Functions over a complexity of 20"]["Total"], "3")

    def test_halstead(self) -> None:
        rows = measures(self.text, "halstead")
        volumes = [item.halstead.volume for item in self.files]
        self.assertEqual(rows["Volume per file"]["Max"], number(max(volumes)))
        efforts = [item.halstead.effort for item in self.files]
        self.assertEqual(rows["Effort per file"]["Max"], number(max(efforts)))
        difficulties = [item.halstead.difficulty for item in self.files]
        self.assertEqual(rows["Difficulty per file"]["Max"], number(max(difficulties)))
        bugs = [item.halstead.bugs for item in self.files]
        self.assertEqual(rows["Estimated bugs per file"]["Total"], number(sum(bugs)))
        self.assertEqual(rows["Estimated bugs per file"]["Max"], number(max(bugs)))
        function_volumes = [item.functions[0].halstead.volume for item in self.files]
        self.assertEqual(
            rows["Volume per function"]["Max"], number(max(function_volumes))
        )

    def test_design(self) -> None:
        rows = measures(self.text, "design")
        self.assertEqual(rows["Classes"]["Total"], "3")
        self.assertEqual(
            (rows["Class complexity"]["Mean"], rows["Class complexity"]["Max"]),
            ("4.00", "9"),
        )
        self.assertEqual(rows["Instance attributes per class"]["Median"], "4.00")
        self.assertEqual(rows["Instance attributes per class"]["Max"], "18")
        self.assertEqual(rows["Contract violations"]["Total"], "0")
        self.assertEqual(rows["Attribute chains too deep"]["Total"], "0")

    def test_limits_of_the_configuration_are_shown_and_applied(self) -> None:
        data = {
            "rules": {
                "function-too-long": {"max-lines": 150},
                "cognitive-complexity": {"max": 1500},
                "too-complex-class": {"max-class-complexity": 5},
                "too-many-instance-attributes": {"max-instance-attributes": 3},
            }
        }
        text = render_report(model_of(self.files, data))
        size = measures(text, "size")
        self.assertEqual(size["Functions over 150 lines of code"]["Total"], "2")
        complexity = measures(text, "complexity")
        self.assertEqual(
            complexity["Functions over a complexity of 1,500"]["Total"], "2"
        )
        design = measures(text, "design")
        self.assertEqual(
            design["Classes over a complexity of 5"]["Total"], "33.3% (1/3)"
        )
        self.assertEqual(
            design["Classes over 3 instance attributes"]["Total"], "66.7% (2/3)"
        )


class DesignColumnsTest(unittest.TestCase):
    def test_contracts_and_chains_are_not_swapped(self) -> None:
        file = summary(violations={"FUR402": 2, "FUR403": 7})
        rows = measures(render_report(model_of([file])), "design")
        self.assertEqual(rows["Contract violations"]["Total"], "2")
        self.assertEqual(rows["Attribute chains too deep"]["Total"], "7")

    def test_each_share_of_classes_has_its_own_limit(self) -> None:
        classes = [class_measures(complexity=80), class_measures(attributes=20)]
        extra = [class_measures(), class_measures()]
        text = render_report(model_of([summary(classes=classes + extra[:1])]))
        rows = measures(text, "design")
        self.assertEqual(
            rows["Classes over a complexity of 70"]["Total"], "33.3% (1/3)"
        )
        self.assertEqual(
            rows["Classes over 14 instance attributes"]["Total"], "33.3% (1/3)"
        )
        text = render_report(model_of([summary(classes=[classes[0]])]))
        rows = measures(text, "design")
        self.assertEqual(
            rows["Classes over 14 instance attributes"]["Total"], "0.0% (0/1)"
        )


class RuleTablesTest(unittest.TestCase):
    def test_each_section_has_the_table_of_its_own_rules(self) -> None:
        text = one_file_report()
        for key, codes in CATEGORY_RULES.items():
            with self.subTest(key=key):
                table = tables_of(section_of(text, key))[1]
                self.assertEqual(table[0], RULE_COLUMNS)
                self.assertEqual([row[0] for row in table[1:]], codes)

    def test_columns(self) -> None:
        file = summary(
            violations={"FUR403": 6},
            suppressed={"FUR403": 3},
            fixable={"FUR403": 2},
        )
        files = [file, summary("b.py", violations={"FUR403": 1})]
        rows = rule_rows(render_report(model_of(files)), "design")
        self.assertEqual(
            next(row for row in rows if row["Code"] == "FUR403"),
            {
                "Code": "FUR403",
                "Name": "demeter-chain",
                "Violations": "7",
                "Files": "2",
                "Suppressed": "3",
                "Fixable": "2",
            },
        )


class SummaryCardsTest(unittest.TestCase):
    def test_every_card_shows_its_own_value(self) -> None:
        files = [
            summary(
                "a.py",
                lines=100,
                code_lines=50,
                functions=[function(), function(), function()],
                classes=[class_measures() for _ in range(4)],
                violations={"FUR101": 5, "FUR001": 2},
                suppressed={"FUR403": 8},
                fixable={"FUR001": 1},
            ),
        ]
        cards = cards_of(
            render_report(model_of([*files, failed("x.py"), failed("y.py")]))
        )
        self.assertEqual(cards["Files analyzed"], "1")
        self.assertEqual(cards["Files in error"], "2")
        self.assertEqual(cards["Lines"], "100")
        self.assertEqual(cards["Lines of code"], "50")
        self.assertEqual(cards["Functions"], "3")
        self.assertEqual(cards["Classes"], "4")
        self.assertEqual(cards["Violations"], "7")
        self.assertEqual(cards["Violations per 1000 lines of code"], "140.00")
        self.assertEqual(cards["Suppressed by foqa"], "8")
        self.assertEqual(cards["Unused foqa directives"], "2")
        self.assertEqual(cards["Available fixes"], "1")

    def test_a_nested_function_is_counted(self) -> None:
        file = summary(functions=[function(), function(nested=True)])
        cards = cards_of(render_report(model_of([file])))
        self.assertEqual(cards["Functions"], "2")


class HeaderTest(unittest.TestCase):
    def test_every_entry_shows_its_own_value(self) -> None:
        config_file = Path("/project/furryp.json")
        text = render_report(
            model_of(
                data={"report": {"title": "My audit"}},
                config_file=config_file,
                timing=TIMING,
            )
        )
        cards = cards_of(text)
        self.assertEqual(cards["furryp"], furryp.__version__)
        self.assertEqual(cards["Python"], platform.python_version())
        self.assertEqual(cards["Project root"], str(Path("/project")))
        self.assertEqual(cards["Configuration file"], str(config_file))
        self.assertEqual(cards["Active rules"], "11")
        self.assertEqual(cards["Generated"], "2026-01-02T03:04:05+00:00")
        self.assertEqual(cards["Analysis time"], "0.00 s")
        self.assertIn("<h1>My audit</h1>", text)
        self.assertIn("<title>My audit</title>", text)

    def test_no_configuration_file(self) -> None:
        cards = cards_of(render_report(model_of()))
        self.assertEqual(cards["Configuration file"], "none, defaults")


class RatingsPlacementTest(unittest.TestCase):
    """Ten files, and a different letter for each category."""

    def setUp(self) -> None:
        counts = {"FUR101": 1, "FUR203": 3, "FUR201": 5, "FUR401": 9}
        self.files = [
            summary(
                f"{index}.py",
                violations={code: 1 for code, count in counts.items() if index < count},
            )
            for index in range(10)
        ]
        self.text = render_report(model_of(self.files))

    def test_cards_of_the_summary(self) -> None:
        self.assertEqual(
            rating_cards_of(self.text),
            {
                "size": ("A", "10.0% (1/10)"),
                "complexity": ("B", "30.0% (3/10)"),
                "halstead": ("C", "50.0% (5/10)"),
                "design": ("E", "90.0% (9/10)"),
            },
        )

    def test_each_section_shows_its_rating_and_its_share(self) -> None:
        expected = {
            "size": ("A", "10.0% (1/10)"),
            "complexity": ("B", "30.0% (3/10)"),
            "halstead": ("C", "50.0% (5/10)"),
            "design": ("E", "90.0% (9/10)"),
        }
        for key, (letter, share) in expected.items():
            with self.subTest(key=key):
                section = section_of(self.text, key)
                self.assertIn(
                    f'<span class="rating rating-{letter}">{letter}</span>', section
                )
                self.assertIn(
                    f"{share} of the analyzed files have at least one violation",
                    section,
                )

    def test_sections_are_open_by_default(self) -> None:
        for key in CATEGORY_RULES:
            with self.subTest(key=key):
                self.assertIn(f'<details class="category" id="{key}" open>', self.text)


class NotRatedSectionsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = render_report(model_of([summary()], {"select": ["FUR101"]}))

    def test_a_section_without_rule_gives_its_reason_and_no_share(self) -> None:
        for key in ("complexity", "halstead", "design"):
            with self.subTest(key=key):
                section = section_of(self.text, key)
                self.assertIn('class="rating rating-none">*</span>', section)
                self.assertIn(
                    "* Not rated: no rule of this category is selected.", section
                )
                self.assertNotIn("of the analyzed files have", section)

    def test_a_section_with_a_rule_has_no_reason(self) -> None:
        section = section_of(self.text, "size")
        self.assertNotIn("Not rated", section)
        self.assertIn("0.0% (0/1) of the analyzed files have", section)

    def test_a_card_without_rating_has_no_share(self) -> None:
        cards = rating_cards_of(self.text)
        self.assertEqual(cards["design"], ("*", "–"))
        self.assertEqual(cards["size"], ("A", "0.0% (0/1)"))

    def test_both_reasons_are_given_in_a_stable_order(self) -> None:
        text = render_report(model_of([], {"select": ["FUR4"]}))
        section = text[text.index('<section id="summary">') :]
        section = section[: section.index("</section>")]
        self.assertLess(
            section.index("no rule of this category"),
            section.index("no file was analyzed"),
        )


class FiguresOfRulesThatDidNotRunTest(unittest.TestCase):
    """A count of violations of a rule that did not run is unknown, not 0."""

    def test_contracts_and_chains_are_judged_separately(self) -> None:
        file = summary(violations={"FUR403": 2})
        rows = measures(
            render_report(model_of([file], {"select": ["FUR403"]})), "design"
        )
        self.assertEqual(rows["Contract violations"]["Total"], "–")
        self.assertEqual(rows["Attribute chains too deep"]["Total"], "2")
        file = summary(violations={"FUR402": 3})
        rows = measures(
            render_report(model_of([file], {"select": ["FUR402"]})), "design"
        )
        self.assertEqual(rows["Contract violations"]["Total"], "3")
        self.assertEqual(rows["Attribute chains too deep"]["Total"], "–")

    def test_columns_of_the_worst_files_too(self) -> None:
        file = summary(violations={"FUR403": 2})
        text = render_report(model_of([file], {"select": ["FUR403"]}))
        row = worst_rows(text, "design")[0]
        self.assertEqual((row["Contracts"], row["Chains"]), ("–", "2"))

    def test_unused_foqa_card(self) -> None:
        cards = cards_of(render_report(model_of([summary()], {"select": ["FUR403"]})))
        self.assertEqual(cards["Unused foqa directives"], "–")
        cards = cards_of(render_report(model_of([summary()], {"select": ["FUR001"]})))
        self.assertEqual(cards["Unused foqa directives"], "0")

    def test_no_reassuring_sentence_in_a_section_that_is_not_rated(self) -> None:
        text = render_report(model_of([summary()], {"select": ["FUR1"]}))
        for key in ("complexity", "halstead", "design"):
            with self.subTest(key=key):
                self.assertNotIn("No file has a violation", section_of(text, key))

    def test_no_reassuring_sentence_without_any_file(self) -> None:
        text = render_report(model_of())
        self.assertNotIn("No file has a violation", text)

    def test_the_sentence_stays_in_a_section_that_is_rated(self) -> None:
        text = render_report(model_of([summary()], {"select": ["FUR1"]}))
        self.assertIn("No file has a violation", section_of(text, "size"))

    def test_measures_stay_whatever_the_selection(self) -> None:
        """A measure does not come from the rule: it is computed for every file."""
        file = summary(
            functions=[function(code_lines=30)],
            classes=[class_measures(complexity=80, attributes=20)],
        )
        text = render_report(model_of([file], {"select": ["FUR102"]}))
        self.assertEqual(
            measures(text, "size")["Functions over 25 lines of code"]["Total"], "1"
        )
        design = measures(text, "design")
        self.assertEqual(design["Classes"]["Total"], "1")
        self.assertEqual(design["Class complexity"]["Max"], "80")
        self.assertEqual(
            design["Classes over a complexity of 70"]["Total"], "100.0% (1/1)"
        )


class AnalysisErrorsSectionTest(unittest.TestCase):
    def section(self, text: str) -> str:
        return text[text.index('<section id="analysis-errors">') :].split("</section>")[
            0
        ]

    def test_no_error_only_says_so(self) -> None:
        section = self.section(render_report(model_of([summary()])))
        self.assertIn("No analysis error.", section)
        self.assertNotIn("These files have no measures", section)
        self.assertNotIn("<table", section)

    def test_with_an_error_the_sentence_and_the_table_appear(self) -> None:
        section = self.section(render_report(model_of([failed("bad.py")])))
        self.assertIn("These files have no measures", section)
        self.assertNotIn("No analysis error.", section)
        self.assertEqual(
            rows_of(tables_of(section)[0]),
            [
                {
                    "File": "bad.py",
                    "Position": "1:5",
                    "Code": "FUR000",
                    "Message": "SyntaxError: invalid syntax",
                }
            ],
        )

    def test_the_list_is_complete_with_every_message_and_position(self) -> None:
        results = [failed(f"f{index:02}.py") for index in range(40)]
        section = self.section(render_report(model_of(results)))
        rows = rows_of(tables_of(section)[0])
        self.assertEqual(len(rows), 40)
        self.assertEqual({row["Position"] for row in rows}, {"1:5"})
        self.assertEqual({row["Code"] for row in rows}, {"FUR000"})
        self.assertEqual(
            {row["Message"] for row in rows}, {"SyntaxError: invalid syntax"}
        )
        self.assertEqual(
            [row["File"] for row in rows], [f"f{index:02}.py" for index in range(40)]
        )

    def test_an_internal_error_has_its_label_in_a_template(self) -> None:
        failure = FileFailure(Path("/project/x.py"), "ValueError: boom")
        model = model_of(failures=[failure])
        self.assertEqual(model.errors[0].message, "ValueError: boom")
        section = self.section(render_report(model))
        row = rows_of(tables_of(section)[0])[0]
        self.assertEqual(row["Message"], "Internal error: ValueError: boom")
        self.assertEqual((row["Position"], row["Code"]), ("–", "–"))
        self.assertIn(
            "Internal error:",
            (TEMPLATES / "internal_error_row.html").read_text(encoding="utf-8"),
        )


class StyleSheetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.css = STYLE_SHEET.read_text(encoding="utf-8")

    def print_block(self) -> str:
        return self.css[self.css.index("@media print") :]

    def test_rating_scale_goes_from_green_to_red(self) -> None:
        hues = {}
        for letter in "abcde":
            value = re.search(rf"--rating-{letter}: #(\w{{6}});", self.css).group(1)
            red, green, blue = (int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))
            hues[letter] = colorsys.rgb_to_hsv(red, green, blue)[0] * 360
        self.assertTrue(70 <= hues["a"] <= 160, hues)
        self.assertTrue(70 <= hues["b"] <= 160, hues)
        self.assertTrue(35 <= hues["c"] <= 65, hues)
        self.assertTrue(10 <= hues["d"] <= 35, hues)
        self.assertTrue(hues["e"] <= 10 or hues["e"] >= 350, hues)
        self.assertGreater(hues["a"], hues["b"])
        self.assertGreater(hues["b"], hues["c"])
        self.assertGreater(hues["c"], hues["d"])

    def test_each_letter_has_its_own_background(self) -> None:
        for letter in "ABCDE":
            with self.subTest(letter=letter):
                block = self.css[self.css.index(f".rating-{letter} {{") :]
                self.assertIn(
                    f"background: var(--rating-{letter.lower()});",
                    block[: block.index("}")],
                )

    def test_print_opens_the_folded_appendix(self) -> None:
        self.assertIn("details::details-content", self.print_block())
        self.assertIn("content-visibility: visible", self.print_block())

    def test_print_keeps_the_colors_of_the_ratings(self) -> None:
        block = self.css[self.css.index("\n.rating {") :]
        self.assertIn("print-color-adjust: exact", block[: block.index("}")])

    def test_summary_keeps_its_folding_marker(self) -> None:
        """``display: flex`` would remove the triangle of ``<summary>``."""
        screen = self.css[: self.css.index("@media print")]
        for match in re.finditer(r"(^|\n)summary \{([^}]*)\}", screen):
            self.assertNotIn("display", match.group(2))
            self.assertNotIn("list-style", match.group(2))


class TemplatesAreSelfContainedTest(unittest.TestCase):
    """Every template is read, even a fragment that a given page does not show."""

    FORBIDDEN = (
        "<script",
        "http",
        "//",
        "src=",
        "<link",
        "<img",
        "<video",
        "<audio",
        "<iframe",
        "<object",
        "<embed",
        "url(",
        "@import",
    )

    def test_no_script_and_no_external_resource(self) -> None:
        for path in sorted(TEMPLATES.iterdir()):
            text = path.read_text(encoding="utf-8").casefold()
            for forbidden in self.FORBIDDEN:
                with self.subTest(template=path.name, forbidden=forbidden):
                    self.assertNotIn(forbidden, text)

    def test_no_event_handler(self) -> None:
        for path in sorted(TEMPLATES.glob("*.html")):
            with self.subTest(template=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIsNone(re.search(r"\son\w+\s*=", text, re.IGNORECASE))

    def test_links_only_point_inside_the_page(self) -> None:
        for path in sorted(TEMPLATES.glob("*.html")):
            links = re.findall(r'href="([^"]*)"', path.read_text(encoding="utf-8"))
            for link in links:
                with self.subTest(template=path.name, link=link):
                    self.assertTrue(link.startswith("#"))
