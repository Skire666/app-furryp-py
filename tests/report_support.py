"""Helpers of the tests of the report: constructed files, HTML checker, fixed clock."""

import html
import re
import unittest
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

from furryp.config.loader import Configuration
from furryp.core.diagnostic import line_span
from furryp.metrics.classes import ClassMetrics
from furryp.metrics.cognitive import Contribution
from furryp.metrics.file_metrics import FunctionMetrics
from furryp.metrics.halstead import Halstead
from furryp.report.files import AnalysisError, FailedFile, FileSummary
from furryp.report.model import ReportModel, Timing, build_report
from tests.support import make_settings, real_registry

ROOT = Path("/project")
FIXED_TIME = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
TIMING = Timing(FIXED_TIME, FIXED_TIME)
NO_HALSTEAD = Halstead(0, 0, 0, 0)
VOID_ELEMENTS = {"meta", "link", "br", "hr", "img", "input"}
SECTION_TITLES = (
    "Summary",
    "Size",
    "Complexity",
    "Halstead",
    "Design",
    "Analysis errors",
    "Appendix: effective configuration",
)
SPAN = line_span(1, 1, 2)


def function(
    name: str = "f",
    code_lines: int = 3,
    cognitive: int = 0,
    nested: bool = False,
    halstead: Halstead = NO_HALSTEAD,
) -> FunctionMetrics:
    """Return the measures of a function; ``cognitive`` is one contribution."""
    contributions = (Contribution("if", 1, cognitive),) if cognitive else ()
    return FunctionMetrics(name, SPAN, nested, code_lines, halstead, contributions)


def class_measures(
    name: str = "C",
    complexity: int = 1,
    attributes: int = 1,
    is_test: bool = False,
    is_dispatch: bool = False,
    is_data: bool = False,
) -> ClassMetrics:
    """Return the measures of a class."""
    return ClassMetrics(
        name, SPAN, complexity, attributes, is_test, is_dispatch, is_data
    )


def summary(
    path: str = "a.py",
    lines: int = 10,
    code_lines: int = 8,
    functions: Sequence[FunctionMetrics] = (),
    classes: Sequence[ClassMetrics] = (),
    halstead: Halstead = NO_HALSTEAD,
    violations: Mapping[str, int] | None = None,
    suppressed: Mapping[str, int] | None = None,
    fixable: Mapping[str, int] | None = None,
) -> FileSummary:
    """Return a file summary built by hand, with known values."""
    return FileSummary(
        path,
        lines,
        code_lines,
        tuple(functions),
        tuple(classes),
        halstead,
        Counter(violations or {}),
        Counter(suppressed or {}),
        Counter(fixable or {}),
    )


def failed(path: str = "bad.py", violations: int = 1) -> FailedFile:
    """Return a file in FUR000."""
    error = AnalysisError(path, "1:5", "FUR000", "SyntaxError: invalid syntax")
    return FailedFile((error,), violations)


def model_of(
    results: Sequence[FileSummary | FailedFile] = (),
    data: dict[str, object] | None = None,
    failures: Sequence = (),
    config_file: Path | None = None,
    timing: Timing = TIMING,
    root: Path = ROOT,
) -> ReportModel:
    """Return the report of ``results`` with a ``furryp.json``-like ``data``."""
    configuration = Configuration(root, config_file, make_settings(data))
    return build_report(configuration, real_registry(), results, failures, root, timing)


class _TableReader(HTMLParser):
    """Read the tables of a document as rows of cell texts."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._cell: list[str] | None = None
        self._span = 1

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "table":
            self.tables.append([])
        elif tag == "tr":
            self.tables[-1].append([])
        elif tag in {"td", "th"}:
            self._cell = []
            self._span = int(dict(attrs).get("colspan", 1))

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None:
            row = self.tables[-1][-1]
            row.extend([""] * (self._span - 1))
            row.append("".join(self._cell).strip())
            self._cell = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def tables_of(text: str) -> list[list[list[str]]]:
    """Return the tables of ``text``; a spanning cell fills its last column."""
    reader = _TableReader()
    reader.feed(text)
    reader.close()
    return reader.tables


def rows_of(table: list[list[str]]) -> list[dict[str, str]]:
    """Return the rows of a table, each cell under the title of its column."""
    head, *rows = table
    return [dict(zip(head, row, strict=True)) for row in rows]


def section_of(text: str, key: str) -> str:
    """Return the section of the category ``key``, and nothing else."""
    start = text.index(f'<details class="category" id="{key}"')
    return text[start : text.index("</details>", start)]


def cards_of(text: str) -> dict[str, str]:
    """Return every term and its value, in the cards and in the header."""
    pairs = re.findall(r"<dt>([^<]*)</dt><dd[^>]*>(.*?)</dd>", text)
    return {key: html.unescape(re.sub(r"<[^>]+>", "", value)) for key, value in pairs}


def rating_cards_of(text: str) -> dict[str, tuple[str, str]]:
    """Return the letter and the share of each card of ratings, by category."""
    pattern = (
        r'href="#(\w+)"><span class="rating rating-\w+">([^<]*)</span>'
        r'<span class="rating-name">[^<]*</span>'
        r'<span class="rating-share">([^<]*)</span>'
    )
    return {key: (letter, share) for key, letter, share in re.findall(pattern, text)}


class WellFormedChecker(HTMLParser):
    """Collect the mismatches between opening and closing tags."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.problems: list[str] = []
        self.tags: Counter[str] = Counter()
        self.headings: list[str] = []
        self._heading = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        self.tags[tag] += 1
        self._heading = tag in {"h2"}
        if self._heading:
            self.headings.append("")
        if tag not in VOID_ELEMENTS:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        self._heading = False
        if not self.stack or self.stack.pop() != tag:
            self.problems.append(f"unexpected </{tag}> at {self.getpos()}")

    def handle_data(self, data: str) -> None:
        if self._heading:
            self.headings[-1] += data


def check_html(test: unittest.TestCase, text: str) -> WellFormedChecker:
    """Assert that ``text`` is a well-formed document; return what was parsed."""
    checker = WellFormedChecker()
    checker.feed(text)
    checker.close()
    test.assertEqual(checker.problems, [])
    test.assertEqual(checker.stack, [])
    test.assertTrue(text.startswith("<!DOCTYPE html>"))
    test.assertEqual(checker.tags["html"], 1)
    return checker
