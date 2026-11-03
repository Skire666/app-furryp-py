"""The diff of a fix below the help (SPEC §5.1): expected texts come from ruff 0.17.3."""

import unittest

from furryp.core.diagnostic import Edit, Fix
from furryp.output.fix_preview import render_fix
from tests.support import (
    CONFIG,
    PYPROJECT,
    TempDirTestCase,
    run_main,
    write_files,
)


def replaced(text: str, old: str, new: str) -> Fix:
    """Return the fix that replaces the only ``old`` of ``text`` by ``new``."""
    start = text.index(old)
    return Fix((Edit(start, start + len(old), new),))


def preview(text: str, old: str, new: str) -> str:
    return "\n".join(render_fix(text, replaced(text, old, new)))


def around_equal_lines(count: int) -> tuple[str, ...]:
    """Return the diff of two changes around ``count`` equal lines."""
    middle = "".join(f"l{i}\n" for i in range(count))
    text = f"a\n{middle}z\n"
    end = len(text) - 1
    return render_fix(text, Fix((Edit(0, 1, "A"), Edit(end - 1, end, "Z"))))


class RenderFixTest(unittest.TestCase):
    def test_a_removed_line_keeps_one_line_of_context(self) -> None:
        text = "a = 1\nb = 2\nc = 3\nimport os\nd = 4\ne = 5\nf = 6\ng = 7\n"
        self.assertEqual(
            preview(text, "import os\n", ""),
            "  |\n3 | c = 3\n  - import os\n4 | d = 4\n  |",
        )

    def test_a_changed_line_is_removed_then_added(self) -> None:
        text = "x = 1  # noqa: F401\ny = 2\n"
        self.assertEqual(
            preview(text, "  # noqa: F401", ""),
            "  |\n  - x = 1  # noqa: F401\n1 + x = 1\n2 | y = 2\n  |",
        )

    def test_a_missing_newline_changes_the_last_line(self) -> None:
        text = "x = 1\ny = 2"
        self.assertEqual(
            preview(text, "y = 2", "y = 2\n"),
            "  |\n1 | x = 1\n  - y = 2\n2 + y = 2\n  |",
        )

    def test_the_last_line_has_no_context_after_it(self) -> None:
        text = "# comment\nimport os\n"
        self.assertEqual(
            preview(text, "import os\n", ""),
            "  |\n1 | # comment\n  - import os\n  |",
        )

    def test_blank_lines_have_no_trailing_blank(self) -> None:
        text = "import sys\nimport os\n\nprint(os, sys)\n"
        self.assertEqual(
            preview(text, "import sys\nimport os\n", "import os\nimport sys\n"),
            "  |\n1 + import os\n2 | import sys\n  - import os\n3 |\n  |",
        )
        text = "from typing import TYPE_CHECKING\nimport os\nv1 = 1\n"
        self.assertEqual(
            preview(text, "import os\n", "\nif TYPE_CHECKING:\n    import os\n"),
            "  |\n"
            "1 | from typing import TYPE_CHECKING\n"
            "  - import os\n"
            "2 +\n"
            "3 + if TYPE_CHECKING:\n"
            "4 +     import os\n"
            "5 | v1 = 1\n"
            "  |",
        )

    def test_trailing_blanks_of_a_line_are_kept(self) -> None:
        self.assertEqual(
            preview("x = 1  \n", "x = 1  ", "x = 1"),
            "  |\n  - x = 1  \n1 + x = 1\n  |",
        )

    def test_tabs_stay_tabs(self) -> None:
        text = "def f():\n\treturn dict(a=1)\n"
        self.assertEqual(
            preview(text, "dict(a=1)", '{"a": 1}'),
            '  |\n1 | def f():\n  - \treturn dict(a=1)\n2 + \treturn {"a": 1}\n  |',
        )

    def test_numbers_are_on_the_left_and_set_the_width(self) -> None:
        lines = "".join(f"v{i} = {i}\n" for i in range(1, 10))
        text = lines + "import json\nw = 1\n"
        self.assertEqual(
            preview(text, "import json\n", ""),
            "   |\n9  | v9 = 9\n   - import json\n10 | w = 1\n   |",
        )

    def test_the_width_is_that_of_the_last_number_shown(self) -> None:
        lines = "".join(f"v{i} = {i}\n" for i in range(1, 9))
        self.assertEqual(
            preview(lines + "import json\nw = 1\n", "import json\n", ""),
            "  |\n8 | v8 = 8\n  - import json\n9 | w = 1\n  |",
        )

    def test_changes_far_apart_are_separated(self) -> None:
        middle = "".join(f"v{i} = os.sep\n" for i in range(1, 13))
        text = f"import os\n{middle}def f(x: int = None): pass\nw1 = 1\nw2 = 2\n"
        start = text.index("def f")
        fix = Fix(
            (
                Edit(10, 10, "from typing import Optional\n"),
                Edit(start, start + len("def f(x: int"), "def f(x: Optional[int]"),
            )
        )
        self.assertEqual(
            render_fix(text, fix),
            (
                "   |",
                "1  | import os",
                "2  + from typing import Optional",
                "3  | v1 = os.sep",
                "-" * 80,
                "14 | v12 = os.sep",
                "   - def f(x: int = None): pass",
                "15 + def f(x: Optional[int] = None): pass",
                "16 | w1 = 1",
                "   |",
            ),
        )

    def test_changes_close_together_stay_in_one_group(self) -> None:
        text = "a\nb\nc\nd\ne\n"
        fix = Fix((Edit(0, 1, "A"), Edit(6, 7, "D")))
        self.assertEqual(
            render_fix(text, fix),
            (
                "  |",
                "  - a",
                "1 + A",
                "2 | b",
                "3 | c",
                "  - d",
                "4 + D",
                "5 | e",
                "  |",
            ),
        )

    def test_up_to_four_equal_lines_are_shown_whole(self) -> None:
        for count in (3, 4):
            with self.subTest(count=count):
                kept = [f"{i + 2} | l{i}" for i in range(count)]
                self.assertEqual(
                    around_equal_lines(count),
                    (
                        "  |",
                        "  - a",
                        "1 + A",
                        *kept,
                        "  - z",
                        f"{count + 2} + Z",
                        "  |",
                    ),
                )

    def test_five_equal_lines_are_cut_with_one_line_on_each_side(self) -> None:
        self.assertEqual(
            around_equal_lines(5),
            (
                "  |",
                "  - a",
                "1 + A",
                "2 | l0",
                "-" * 80,
                "6 | l4",
                "  - z",
                "7 + Z",
                "  |",
            ),
        )

    def test_only_some_control_characters_are_replaced_as_in_ruff(self) -> None:
        text = 'x = "\x07\x08\x1b\x7f\x0c"; y = 1\n'
        self.assertEqual(
            preview(text, "y = 1", "y = 2"),
            "  |\n"
            '  - x = "\u2407\u2408\u241b\u2421\x0c"; y = 1\n'
            '1 + x = "\u2407\u2408\u241b\u2421\x0c"; y = 2\n'
            "  |",
        )

    def test_a_fix_that_changes_nothing_shows_nothing(self) -> None:
        self.assertEqual(render_fix("x = 1\n", Fix((Edit(0, 1, "x"),))), ())

    def test_crlf_is_not_shown(self) -> None:
        self.assertEqual(
            preview("x = 1\r\ny = 2\r\n", "y = 2", "y = 3"),
            "  |\n1 | x = 1\n  - y = 2\n2 + y = 3\n  |",
        )

    def test_repeated_blank_lines_keep_the_context_after_them(self) -> None:
        text = "import a\n\ndef f(): pass\n"
        self.assertEqual(
            preview(text, "\ndef", "\n\ndef"),
            "  |\n2 |\n3 +\n4 | def f(): pass\n  |",
        )


class CheckOutputTest(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        write_files(self.root, {PYPROJECT: ""})

    def test_the_diff_follows_the_help(self) -> None:
        write_files(self.root, {"a.py": "x = 1\ny = 2  # foqa:FUR102\nz = 3\n"})
        code, stdout, _ = run_main(["check", "a.py"], self.root)
        self.assertEqual(code, 1)
        self.assertEqual(
            stdout,
            "unused-foqa [FUR001] [*]: Unused `foqa` directive (unused: `FUR102`)\n"
            " --> a.py:2:8\n"
            "  |\n"
            "1 | x = 1\n"
            "2 | y = 2  # foqa:FUR102\n"
            "  |        ^^^^^^^^^^^^^\n"
            "3 | z = 3\n"
            "  |\n"
            "help: Remove unused `foqa` directive\n"
            "  |\n"
            "1 | x = 1\n"
            "  - y = 2  # foqa:FUR102\n"
            "2 + y = 2\n"
            "3 | z = 3\n"
            "  |\n"
            "\n"
            "Found 1 error.\n"
            "[*] 1 fixable with `--fix`.\n",
        )

    def test_a_diagnostic_without_fix_has_no_diff(self) -> None:
        write_files(self.root, {"a.py": "def f(:\n"})
        _, stdout, _ = run_main(["check", "--select", "FUR000", "a.py"], self.root)
        self.assertNotIn("\n  |\nFound", stdout)
        self.assertNotIn(" + ", stdout)

    def test_nothing_is_shown_once_fixed(self) -> None:
        write_files(self.root, {"a.py": "x = 1  # foqa:FUR102\n"})
        code, stdout, _ = run_main(["check", "--fix", "a.py"], self.root)
        self.assertEqual((code, stdout), (0, "Found 1 error (1 fixed, 0 remaining).\n"))

    def test_statistics_and_diff_modes_do_not_show_it(self) -> None:
        write_files(self.root, {"a.py": "x = 1  # foqa:FUR102\n"})
        _, stdout, _ = run_main(["check", "--statistics", "a.py"], self.root)
        self.assertNotIn(" + ", stdout)
        _, stdout, _ = run_main(["check", "--diff", "a.py"], self.root)
        self.assertTrue(stdout.startswith("--- a.py\n+++ a.py\n"))


if __name__ == "__main__":
    unittest.main()
