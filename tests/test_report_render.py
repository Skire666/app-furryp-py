"""Rendering of the report: sections, escaping, templates, writing (SPEC §12.2)."""

import ast
import re
import unittest
from importlib import resources
from pathlib import Path
from unittest import mock

from furryp.core.errors import FileFailure, ReportWriteError
from furryp.report import render
from furryp.report.categories import Share
from furryp.report.render import (
    Html,
    fill,
    format_value,
    render_report,
    write_report,
)
from tests.report_support import (
    ROOT,
    SECTION_TITLES,
    check_html,
    class_measures,
    failed,
    function,
    model_of,
    summary,
)
from tests.support import REPO_ROOT, TempDirTestCase

REPORT_PACKAGE = REPO_ROOT / "furryp" / "report"
TEMPLATES = REPORT_PACKAGE / "templates"
HTML_TAG = re.compile(r"</?[a-zA-Z!][^<>]*>")
EVERY_VIOLATION = {
    "FUR101": 1,
    "FUR203": 1,
    "FUR201": 1,
    "FUR403": 1,
    "FUR402": 1,
}


def rich_model(path: str = "pkg/a.py", name: str = "load", data: dict | None = None):
    """Return a report with a line in every table."""
    file = summary(
        path,
        functions=[function(name, cognitive=30)],
        classes=[class_measures(name)],
        violations=EVERY_VIOLATION,
        suppressed={"FUR102": 1},
        fixable={"FUR403": 1},
    )
    return model_of([file, failed()], data)


class SectionsTest(unittest.TestCase):
    def test_well_formed_with_every_section(self) -> None:
        checker = check_html(self, render_report(rich_model()))
        for title in SECTION_TITLES:
            with self.subTest(title=title):
                self.assertIn(title, checker.headings)

    def test_empty_report_is_well_formed_with_every_section(self) -> None:
        checker = check_html(self, render_report(model_of()))
        self.assertEqual(checker.headings, list(SECTION_TITLES))

    def test_categories_appear_in_the_order_of_the_spec(self) -> None:
        text = render_report(rich_model())
        ids = re.findall(r'<details class="category" id="(\w+)"', text)
        self.assertEqual(ids, ["size", "complexity", "halstead", "design"])

    def test_labels_of_the_spec(self) -> None:
        text = render_report(rich_model())
        self.assertIn("Suppressed", text)
        self.assertIn("Violations per 1000 lines of code", text)
        self.assertIn("Unused foqa directives", text)
        self.assertIn("Available fixes", text)

    def test_no_placeholder_is_left(self) -> None:
        text = render_report(rich_model())
        self.assertNotIn("$", text)

    def test_appendix_is_folded_and_holds_the_configuration(self) -> None:
        text = render_report(rich_model(data={"report": {"title": "Audit"}}))
        appendix = text[text.index('<section id="appendix">') :]
        self.assertIn("<details>", appendix)
        self.assertNotIn("<details open", appendix)
        self.assertIn("&quot;top-n&quot;: 10", appendix)
        self.assertIn("&quot;title&quot;: &quot;Audit&quot;", appendix)


class SelfContainedTest(unittest.TestCase):
    def test_no_script_and_no_external_resource(self) -> None:
        text = render_report(rich_model()).casefold()
        for forbidden in (
            "<script",
            "http",
            "<link",
            "<img",
            "<iframe",
            "url(",
            "@import",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)

    def test_links_only_point_inside_the_page(self) -> None:
        text = render_report(rich_model())
        links = re.findall(r'href="([^"]*)"', text)
        self.assertTrue(links)
        for link in links:
            self.assertTrue(link.startswith("#"), link)
            self.assertIn(f'id="{link[1:]}"', text)

    def test_print_styles_exist(self) -> None:
        self.assertIn("@media print", render_report(model_of()))

    def test_each_letter_has_its_style_and_stays_in_the_page(self) -> None:
        text = render_report(rich_model())
        for letter in "ABCDE":
            self.assertIn(f".rating-{letter} {{", text)
        self.assertIn('class="rating rating-E">E</span>', text)


class EscapingTest(unittest.TestCase):
    HOSTILE = "<img src=x>&'\""

    def assert_only_escaped(self, text: str) -> None:
        self.assertNotIn(self.HOSTILE, text)
        self.assertNotIn("<img", text)
        self.assertIn("&lt;img src=x&gt;&amp;", text)

    def test_path_in_every_table_of_worst_files(self) -> None:
        text = render_report(rich_model(path=self.HOSTILE))
        check_html(self, text)
        self.assert_only_escaped(text)
        self.assertEqual(text.count("&lt;img src=x&gt;&amp;"), 4)

    def test_function_name(self) -> None:
        self.assert_only_escaped(render_report(rich_model(name=self.HOSTILE)))

    def test_title(self) -> None:
        text = render_report(rich_model(data={"report": {"title": self.HOSTILE}}))
        self.assert_only_escaped(text)
        self.assertIn("<title>&lt;img", text)

    def test_analysis_error(self) -> None:
        text = render_report(model_of([failed(self.HOSTILE)]))
        check_html(self, text)
        self.assert_only_escaped(text)

    def test_internal_error_message(self) -> None:
        failure = FileFailure(ROOT / "x.py", self.HOSTILE)
        self.assert_only_escaped(render_report(model_of(failures=[failure])))

    def test_config_file(self) -> None:
        text = render_report(model_of(config_file=Path(self.HOSTILE)))
        self.assert_only_escaped(text)

    def test_project_root(self) -> None:
        self.assert_only_escaped(render_report(model_of(root=Path(self.HOSTILE))))

    def test_only_a_rendered_fragment_is_not_escaped(self) -> None:
        self.assertEqual(fill("no_config_file", {}), Html("<em>none, defaults</em>"))
        self.assertIn("&lt;b&gt;", fill("banner", {"count": "<b>"}).text)
        self.assertIn("<b>", fill("banner", {"count": Html("<b>")}).text)


class RatingDisplayTest(unittest.TestCase):
    def test_not_rated_shows_a_star_and_its_reason(self) -> None:
        text = render_report(model_of([summary()], {"select": ["FUR4"]}))
        self.assertIn('class="rating rating-none">*</span>', text)
        self.assertIn("* Not rated: no rule of this category is selected.", text)
        self.assertIn('class="rating rating-A">A</span>', text)

    def test_the_reason_is_given_once_in_the_summary(self) -> None:
        text = render_report(model_of([summary()], {"select": ["FUR4"]}))
        section = text[text.index('<section id="summary">') : text.index("</section>")]
        self.assertEqual(section.count("* Not rated"), 1)

    def test_no_file_gives_another_reason(self) -> None:
        text = render_report(model_of())
        self.assertIn("* Not rated: no file was analyzed.", text)
        self.assertNotIn("no rule of this category", text)

    def test_a_rated_report_has_no_star(self) -> None:
        text = render_report(model_of([summary()]))
        self.assertNotIn("Not rated", text)
        self.assertNotIn('rating-none">', text)

    def test_the_share_is_shown_with_its_counts(self) -> None:
        files = [summary("a.py", violations={"FUR403": 1}), summary("b.py")]
        self.assertIn("50.0% (1/2)", render_report(model_of(files)))


class BannerTest(unittest.TestCase):
    def test_a_file_in_error_raises_the_banner_with_a_link(self) -> None:
        text = render_report(model_of([failed("a.py"), failed("b.py")]))
        self.assertIn('role="alert"', text)
        self.assertIn("files not analyzed: 2.", text)
        self.assertIn('href="#analysis-errors"', text)
        self.assertLess(text.index('role="alert"'), text.index('id="summary"'))

    def test_an_internal_error_raises_the_banner(self) -> None:
        failure = FileFailure(ROOT / "x.py", "ValueError: boom")
        text = render_report(model_of(failures=[failure]))
        self.assertIn("files not analyzed: 1.", text)
        self.assertIn("Internal error: ValueError: boom", text)

    def test_no_error_no_banner(self) -> None:
        text = render_report(model_of([summary()]))
        self.assertNotIn('role="alert"', text)
        self.assertIn("No analysis error.", text)


class EmptyTablesTest(unittest.TestCase):
    def test_a_clean_file_gives_empty_worst_tables(self) -> None:
        text = render_report(model_of([summary()]))
        self.assertEqual(text.count("No file has a violation in this category."), 4)

    def test_a_table_with_rows_has_no_empty_message(self) -> None:
        text = render_report(rich_model())
        self.assertNotIn("No file has a violation in this category.", text)


class FormatTest(unittest.TestCase):
    def test_values(self) -> None:
        cases = (
            (None, "–"),
            (0, "0"),
            (1234567, "1,234,567"),
            (0.5, "0.50"),
            (1234.567, "1,234.57"),
            ("x", "x"),
            (Share(1, 3), "33.3% (1/3)"),
            (Share(0, 0), "–"),
        )
        for value, shown in cases:
            with self.subTest(value=value):
                self.assertEqual(format_value(value), shown)


class TemplatesTest(unittest.TestCase):
    def test_every_template_is_used(self) -> None:
        used: list[str] = []
        original = render.read_template

        def recording(name: str) -> str:
            used.append(name)
            return original(name)

        render._template.cache_clear()
        self.addCleanup(render._template.cache_clear)
        with mock.patch.object(render, "read_template", recording):
            render_report(rich_model())
            render_report(model_of(config_file=ROOT / "c.json"))
            render_report(model_of([summary()], {"select": ["FUR4"]}))
            failure = FileFailure(ROOT / "x.py", "ValueError: boom")
            render_report(model_of([summary()], failures=[failure]))
        files = {path.name for path in TEMPLATES.iterdir()}
        self.assertEqual(set(used), files)

    def test_python_holds_no_html(self) -> None:
        for path in REPORT_PACKAGE.glob("*.py"):
            tree = ast.parse(path.read_bytes())
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    with self.subTest(path=path.name, line=node.lineno):
                        self.assertIsNone(HTML_TAG.search(node.value))

    def test_templates_are_read_as_utf8(self) -> None:
        """The en dash of a template stays one character, whatever the locale."""
        package = resources.files("furryp.report")
        text = package.joinpath("templates", "halstead.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("–", text)
        self.assertIn("–", render.read_template("halstead.html"))

    def test_final_line_end_of_a_template_is_dropped(self) -> None:
        self.assertFalse(render.read_template("rated.html").endswith("\n"))


class DeterminismTest(unittest.TestCase):
    def test_same_model_same_text(self) -> None:
        self.assertEqual(render_report(rich_model()), render_report(rich_model()))

    def test_same_files_in_another_order_same_text(self) -> None:
        files = [
            summary(f"{name}.py", violations={"FUR403": 1}) for name in ("c", "a", "b")
        ]
        self.assertEqual(
            render_report(model_of(files)),
            render_report(model_of(list(reversed(files)))),
        )


class WriteTest(TempDirTestCase):
    def test_utf8_and_line_feeds(self) -> None:
        target = self.root / "report.html"
        write_report(target, "é — ☃\nnext\n")
        self.assertEqual(target.read_bytes(), "é — ☃\nnext\n".encode())

    def test_missing_parent_directories_are_created(self) -> None:
        target = self.root / "deep" / "er" / "report.html"
        write_report(target, "x")
        self.assertEqual(target.read_bytes(), b"x")

    def test_overwrites_an_existing_report(self) -> None:
        target = self.root / "report.html"
        target.write_bytes(b"old")
        write_report(target, "new")
        self.assertEqual(target.read_bytes(), b"new")

    def test_a_directory_cannot_be_written(self) -> None:
        with self.assertRaises(ReportWriteError) as caught:
            write_report(self.root, "x")
        self.assertIn("Failed to write report", str(caught.exception))

    def test_a_parent_that_is_a_file_cannot_be_used(self) -> None:
        (self.root / "file").write_bytes(b"")
        with self.assertRaises(ReportWriteError):
            write_report(self.root / "file" / "report.html", "x")

    def test_a_character_that_cannot_be_encoded_does_not_lose_the_report(self) -> None:
        """A file name that is not valid UTF-8 gives a surrogate under Linux."""
        target = self.root / "report.html"
        write_report(target, "bad\udc80name")
        self.assertEqual(target.read_bytes(), b"bad?name")
