"""Terminal output (SPEC §5.1, §5.2) and ``--statistics`` (SPEC §5.4)."""

import os
import unittest
from pathlib import Path

from furryp.core.diagnostic import (
    FILE_START,
    Diagnostic,
    Edit,
    Fix,
    Position,
    Span,
    line_span,
)
from furryp.core.source import read_source
from furryp.lint.runner import FileReport
from furryp.output.snippet import build_snippet, display_width
from furryp.output.statistics import render_statistics
from furryp.output.terminal import (
    Entry,
    collect_entries,
    render_check,
    render_footer,
)
from tests.support import REPO_ROOT, TempDirTestCase, text_source, write_files

SNAPSHOTS = REPO_ROOT / "tests" / "snapshots"
SNAPSHOT_SEPARATOR = "\\"
UNUSED_DIRECTIVE = "  # foqa:FUR102"
A_FIX = Fix((Edit(0, 0, "# why\n"),))
MAIN_TAIL = (
    '    base = os.environ.get("LOCALAPPDATA", str(Path("~").expanduser()))',
    '    path_browser = str(Path(base) / C_APP_NAME / "ms-playwright")',
    "    return path_browser  # foqa:FUR102",
)
SERVICE_LINES = (
    "            self._wire_page_crash_listener(page)",
    "",
    "    def get_args_for_stealth(self) -> list[str]:",
    (
        "        # Resolve to absolute path — Chromium executable is not Python,"
        " so relative paths are unsafe."
    ),
    "        ext_path = str(Path(self._chromium_extensions_dir).resolve())",
)


def read_snapshot(name: str) -> str:
    """Return a snapshot with its ``\\`` separators replaced by ``os.sep``."""
    text = (SNAPSHOTS / name).read_text(encoding="utf-8")
    return text.replace(SNAPSHOT_SEPARATOR, os.sep)


def diagnostic(
    span: Span, help_text: str = "Do it", fix: Fix | None = None
) -> Diagnostic:
    return Diagnostic(
        "FUR999", "some-rule", "Message", Path("a.py"), span, help_text, fix
    )


def render(lines: tuple[str, ...] | None, *diagnostics: Diagnostic) -> str:
    source = None if lines is None else text_source("\n".join(lines))
    return render_check([Entry("a.py", item, source) for item in diagnostics])


class ReferenceSnapshotTest(TempDirTestCase):
    """The reference example of SPEC §5.1, character for character."""

    def write_sources(self) -> tuple[Path, Path]:
        main = [f"# line {number}" for number in range(1, 99)] + list(MAIN_TAIL)
        service = [f"# line {number}" for number in range(1, 112)]
        service += [*SERVICE_LINES, "        return [ext_path]"]
        write_files(
            self.root,
            {
                "__src__/main.py": "\n".join(main) + "\n",
                "__src__/services/browser_playwright_service.py": "\n".join(service)
                + "\n",
            },
        )
        return (
            self.root / "__src__" / "main.py",
            self.root / "__src__" / "services" / "browser_playwright_service.py",
        )

    def test_reference_example(self) -> None:
        main, service = self.write_sources()
        text = read_source(main, "").text
        start = text.index(UNUSED_DIRECTIVE)
        unused = Diagnostic(
            "FUR001",
            "unused-foqa",
            "Unused `foqa` directive (unused: `FUR102`)",
            main,
            line_span(101, 26, 39),
            "Remove unused `foqa` directive",
            Fix((Edit(start, start + len(UNUSED_DIRECTIVE), ""),)),
        )
        too_long = Diagnostic(
            "FUR101",
            "function-too-long",
            "Function `get_args_for_stealth` has too many lines of code (31 > 25)",
            service,
            line_span(114, 9, 29),
            "Long functions are hard to read and test; consider splitting this one",
        )
        reports = [
            FileReport(service, read_source(service, ""), (too_long,), ()),
            FileReport(main, read_source(main, ""), (unused,), ()),
        ]
        output = render_check(collect_entries(reports, self.root)) + "\n"
        self.assertEqual(output, read_snapshot("reference.txt"))


class RenderingTest(unittest.TestCase):
    def test_blank_lines_are_trimmed_at_both_ends(self) -> None:
        lines = ("", "a = 1", "", "b = 2", "")
        self.assertEqual(
            render(lines, diagnostic(line_span(4, 1, 2))),
            "some-rule [FUR999]: Message\n"
            " --> a.py:4:1\n"
            "  |\n"
            "2 | a = 1\n"
            "3 |\n"
            "4 | b = 2\n"
            "  | ^\n"
            "help: Do it\n\n"
            "Found 1 error.",
        )

    def test_tabs_are_four_spaces(self) -> None:
        lines = ("\tx = 1\t# c",)
        output = render(lines, diagnostic(line_span(1, 8, 11)))
        self.assertIn("1 |     x = 1    # c\n  | " + " " * 13 + "^^^\n", output)
        output = render(lines, diagnostic(line_span(1, 7, 10)))
        self.assertIn("\n  | " + " " * 9 + "^" * 6 + "\n", output)

    def test_span_on_several_lines_after_code_like_ruff(self) -> None:
        lines = ("def f():", "    prev = 1", "    return dict(", "        a=1,")
        lines += ("    ).keys()", "", "", "after = 2")
        span = Span(Position(3, 12), Position(5, 6))
        self.assertEqual(
            render(lines, diagnostic(span)),
            "some-rule [FUR999]: Message\n"
            " --> a.py:3:12\n"
            "  |\n"
            "1 |   def f():\n"
            "2 |       prev = 1\n"
            "3 |       return dict(\n"
            "  |  ____________^\n"
            "4 | |         a=1,\n"
            "5 | |     ).keys()\n"
            "  | |_____^\n"
            "help: Do it\n\n"
            "Found 1 error.",
        )

    def test_span_on_several_lines_at_the_start_of_a_line_like_ruff(self) -> None:
        lines = ("def f():", "    prev = 1", "    dict(", "        a=1,")
        lines += ("    )", "    after = 2")
        span = Span(Position(3, 5), Position(5, 6))
        self.assertEqual(
            render(lines, diagnostic(span)),
            "some-rule [FUR999]: Message\n"
            " --> a.py:3:5\n"
            "  |\n"
            "1 |   def f():\n"
            "2 |       prev = 1\n"
            "3 | /     dict(\n"
            "4 | |         a=1,\n"
            "5 | |     )\n"
            "  | |_____^\n"
            "6 |       after = 2\n"
            "  |\n"
            "help: Do it\n\n"
            "Found 1 error.",
        )

    def test_span_on_several_lines_keeps_inner_blank_lines(self) -> None:
        lines = ("x = (", "", "    1,", ")", "", "y = 1", "z = 2", "w = 3")
        span = Span(Position(1, 5), Position(4, 2))
        self.assertEqual(
            render(lines, diagnostic(span)),
            "some-rule [FUR999]: Message\n"
            " --> a.py:1:5\n"
            "  |\n"
            "1 |   x = (\n"
            "  |  _____^\n"
            "2 | |\n"
            "3 | |     1,\n"
            "4 | | )\n"
            "  | |_^\n"
            "5 |\n"
            "6 |   y = 1\n"
            "  |\n"
            "help: Do it\n\n"
            "Found 1 error.",
        )

    def test_a_span_on_the_whole_file_has_no_excerpt_like_ruff(self) -> None:
        self.assertEqual(
            render(("x = 1",), diagnostic(FILE_START)),
            "some-rule [FUR999]: Message\n--> a.py:1:1\nhelp: Do it\n\nFound 1 error.",
        )

    def test_width_follows_the_largest_line_number(self) -> None:
        lines = tuple(f"x{number} = 1" for number in range(1, 12))
        output = render(lines, diagnostic(line_span(9, 1, 3)))
        self.assertIn("  --> a.py:9:1\n   |\n 7 | x7 = 1\n", output)
        self.assertIn("11 | x11 = 1\n   |\nhelp: Do it", output)

    def test_span_past_the_end_of_the_line(self) -> None:
        self.assertIn("1 | x\n  |  ^\n", render(("x",), diagnostic(line_span(1, 2, 2))))

    def test_unreadable_source_has_no_excerpt(self) -> None:
        """No line number is shown: ``W`` is 0, as ruff prints ``--> path``."""
        self.assertEqual(
            render(None, diagnostic(line_span(1, 1, 1))),
            "some-rule [FUR999]: Message\n--> a.py:1:1\nhelp: Do it\n\nFound 1 error.",
        )

    def test_footer(self) -> None:
        self.assertEqual(render_check([]), "All checks passed!")
        span = line_span(1, 1, 2)
        output = render(("x",), diagnostic(span), diagnostic(span, fix=A_FIX))
        self.assertTrue(
            output.endswith("\n\nFound 2 errors.\n[*] 1 fixable with `--fix`.")
        )
        self.assertIn("some-rule [FUR999] [*]: Message\n", output)

    def test_footer_after_fix(self) -> None:
        """As ruff 0.17.3: the counts in brackets only when a fix was applied."""
        span = line_span(1, 1, 2)
        remaining = [diagnostic(span), diagnostic(span, fix=A_FIX)]
        self.assertEqual(
            render_footer(remaining, fixed=3),
            "Found 5 errors (3 fixed, 2 remaining).\n[*] 1 fixable with `--fix`.",
        )
        self.assertEqual(
            render_footer([], fixed=1), "Found 1 error (1 fixed, 0 remaining)."
        )
        self.assertEqual(render_footer(remaining[:1], fixed=0), "Found 1 error.")
        self.assertEqual(render_footer([], fixed=0), "All checks passed!")


class DisplayedCharactersTest(unittest.TestCase):
    """Expected texts come from ruff 0.17.3."""

    def test_display_width(self) -> None:
        for text, width in (
            ("", 0),
            ("abc", 3),
            ("\u00e9t\u00e9", 3),
            ("\u65e5\u672c\u8a9e", 6),
            ("\uff21", 2),
            ("e\u0301", 1),
            ("\u200b", 0),
        ):
            with self.subTest(text=text):
                self.assertEqual(display_width(text), width)

    def test_the_underline_starts_at_the_display_column(self) -> None:
        line = 'x = "\u65e5\u672c\u8a9e" + a'
        self.assertEqual(
            build_snippet([line], line_span(1, 13, 14)).lines,
            ("  |", f"1 | {line}", "  |                ^"),
        )

    def test_the_underline_is_as_long_as_the_display_width(self) -> None:
        line = "\u65e5\u672c\u8a9e + 1"
        self.assertEqual(
            build_snippet([line], line_span(1, 1, 4)).lines,
            ("  |", f"1 | {line}", "  | ^^^^^^"),
        )

    def test_a_span_on_several_lines_opens_at_the_display_column(self) -> None:
        lines = ['x = "\u65e5\u672c\u8a9e" + dict(', "    a=1,", ")"]
        span = Span(Position(1, 13), Position(3, 2))
        self.assertEqual(
            build_snippet(lines, span).lines,
            (
                "  |",
                f"1 |   {lines[0]}",
                "  |  ________________^",
                "2 | |     a=1,",
                "3 | | )",
                "  | |_^",
            ),
        )

    def test_a_span_on_several_lines_closes_at_the_display_column(self) -> None:
        lines = ["y = dict(", '    b="\u65e5", c=1)']
        span = Span(Position(1, 5), Position(2, 16))
        self.assertEqual(
            build_snippet(lines, span).lines,
            (
                "  |",
                f"1 |   {lines[0]}",
                "  |  _____^",
                f"2 | | {lines[1]}",
                "  | |________________^",
            ),
        )

    def test_invisible_characters_are_replaced_as_in_ruff(self) -> None:
        for char, shown in (
            ("\x00", "\u2400"),
            ("\x07", "\u2407"),
            ("\x0c", "\u240c"),
            ("\x1b", "\u241b"),
            ("\x1f", "\u241f"),
            ("\x7f", "\u2421"),
            ("\t", "    "),
            ("\u200d", ""),
            ("\u202a", "\ufffd"),
            ("\u202e", "\ufffd"),
            ("\u2066", "\ufffd"),
            ("\u2069", "\ufffd"),
        ):
            with self.subTest(char=char):
                offset = len(f'x = "{shown}"; y = ')
                self.assertEqual(
                    build_snippet(
                        [f'x = "{char}"; y = dict(a=1)'], line_span(1, 14, 23)
                    ).lines,
                    (
                        "  |",
                        f'1 | x = "{shown}"; y = dict(a=1)',
                        "  | " + " " * offset + "^" * 9,
                    ),
                )

    def test_a_line_of_form_feed_alone_is_blank(self) -> None:
        self.assertEqual(
            build_snippet(["import os", "\x0c"], line_span(1, 8, 10)).lines,
            ("  |", "1 | import os", "  |        ^^"),
        )


class OrderTest(TempDirTestCase):
    def test_sorted_by_path_line_column_code(self) -> None:
        def make(path: Path, line: int, column: int, code: str) -> Diagnostic:
            return Diagnostic(
                code, "r", "m", path, line_span(line, column, column + 1), "Do"
            )

        first, second = self.root / "a.py", self.root / "b.py"
        report_b = FileReport(second, None, (make(second, 1, 1, "FUR001"),), ())
        report_a = FileReport(
            first,
            None,
            (
                make(first, 2, 1, "FUR001"),
                make(first, 1, 5, "FUR001"),
                make(first, 1, 5, "FUR000"),
            ),
            (),
        )
        entries = collect_entries([report_b, report_a], self.root)
        self.assertEqual(
            [
                (e.display, e.diagnostic.span.start.line, e.diagnostic.code)
                for e in entries
            ],
            [
                ("a.py", 1, "FUR000"),
                ("a.py", 1, "FUR001"),
                ("a.py", 2, "FUR001"),
                ("b.py", 1, "FUR001"),
            ],
        )

    def test_path_outside_the_current_directory_is_absolute(self) -> None:
        outside = self.root.parent / "elsewhere.py"
        report = FileReport(outside, None, (diagnostic(line_span(1, 1, 1)),), ())
        self.assertEqual(collect_entries([report], self.root)[0].display, str(outside))


class StatisticsTest(unittest.TestCase):
    def test_counts(self) -> None:
        def make(code: str, name: str, fix: Fix | None = None) -> Diagnostic:
            return Diagnostic(
                code, name, "m", Path("a.py"), line_span(1, 1, 2), "Do", fix
            )

        diagnostics = [make("FUR403", "demeter-chain")] * 10
        diagnostics += [
            make("FUR001", "unused-foqa"),
            make("FUR001", "unused-foqa", A_FIX),
        ]
        diagnostics += [make("FUR102", "file-too-long")] * 2
        self.assertEqual(
            render_statistics(diagnostics),
            "10\tFUR403\t[ ] demeter-chain\n"
            " 2\tFUR001\t[*] unused-foqa\n"
            " 2\tFUR102\t[ ] file-too-long\n"
            "Found 14 errors.\n"
            "[*] 1 fixable with `--fix`.",
        )

    def test_no_marker_when_no_rule_is_fixable(self) -> None:
        diagnostic = Diagnostic(
            "FUR102", "file-too-long", "m", Path("a.py"), line_span(1, 1, 2), "Do"
        )
        self.assertEqual(
            render_statistics([diagnostic]),
            "1\tFUR102\tfile-too-long\nFound 1 error.",
        )

    def test_no_violation_shows_nothing(self) -> None:
        self.assertEqual(render_statistics([]), "")


if __name__ == "__main__":
    unittest.main()
