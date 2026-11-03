"""Fix of FUR001 (SPEC §7.3, FUR001)."""

import unittest

from furryp.fix.engine import fix_report
from tests.support import FLAGGED, linter_with, text_source


def fixed(text: str, data: dict[str, object] | None = None) -> str:
    """Return ``text`` once fixed with the shipped rules."""
    linter = linter_with(data=data)
    return fix_report(linter, linter.check_source(text_source(text))).text


class UnusedFoqaFixTest(unittest.TestCase):
    def assert_fixes(
        self, cases: list[tuple[str, str]], data: dict[str, object] | None = None
    ) -> None:
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(fixed(text, data), expected)
                self.assertEqual(fixed(expected, data), expected)

    def test_directive_is_rewritten_with_the_codes_that_served(self) -> None:
        self.assert_fixes(
            [
                (f"{FLAGGED}  # foqa:FUR403,FUR102\n", f"{FLAGGED}  # foqa:FUR403\n"),
                (
                    f"{FLAGGED}  # FOQA: FUR102 , FUR403\n",
                    f"{FLAGGED}  # foqa:FUR403\n",
                ),
                (
                    f"{FLAGGED}  # foqa:file-too-long,demeter-chain  # why\n",
                    f"{FLAGGED}  # foqa:demeter-chain  # why\n",
                ),
                (
                    f"{FLAGGED}  # foqa:FUR403,FUR999,FUR403\n",
                    f"{FLAGGED}  # foqa:FUR403\n",
                ),
                (
                    f"# furryp: foqa:FUR102,FUR403\n{FLAGGED}\n",
                    f"# furryp: foqa:FUR403\n{FLAGGED}\n",
                ),
            ]
        )

    def test_directive_that_is_not_reported_is_kept(self) -> None:
        self.assert_fixes(
            [
                (
                    f"{FLAGGED}  # foqa:FUR403,FUR999\n",
                    f"{FLAGGED}  # foqa:FUR403,FUR999\n",
                )
            ]
        )

    def test_empty_directive_is_removed(self) -> None:
        self.assert_fixes(
            [
                ("x = 1  # foqa:FUR102\n", "x = 1\n"),
                ("x = 1 # foqa:FUR102   \n", "x = 1\n"),
                ("x = 1  # foqa\n", "x = 1\n"),
                ("t = (1,  # foqa:FUR102\n     2)\n", "t = (1,\n     2)\n"),
            ]
        )

    def test_other_comment_is_kept(self) -> None:
        self.assert_fixes(
            [
                ("x = 1  # foqa:FUR102  # why\n", "x = 1  # why\n"),
                ("x = 1  # why  # foqa:FUR102\n", "x = 1  # why\n"),
                ("x = 1  # a # foqa:FUR102 # b\n", "x = 1  # a # b\n"),
                (
                    "if x:\n    # foqa:FUR102  # keep\n    y = 1\n",
                    "if x:\n    # keep\n    y = 1\n",
                ),
            ]
        )

    def test_line_left_empty_is_deleted(self) -> None:
        self.assert_fixes(
            [
                ("x = 1\n# foqa:FUR102\ny = 2\n", "x = 1\ny = 2\n"),
                ("# furryp: foqa:FUR102\nx = 1\n", "x = 1\n"),
                (
                    "x = 1\r\n    # foqa:FUR102\r\n\r\ny = 2\r\n",
                    "x = 1\r\n\r\ny = 2\r\n",
                ),
            ]
        )

    def test_a_line_directive_under_a_file_directive_is_removed(self) -> None:
        self.assert_fixes(
            [
                (
                    f"# furryp: foqa:FUR403\n{FLAGGED}  # foqa:FUR403\n",
                    f"# furryp: foqa:FUR403\n{FLAGGED}\n",
                ),
            ]
        )

    def test_a_blanket_file_directive_is_left_alone(self) -> None:
        # As ruff: it exempts its whole file from FUR001, and so from its fix.
        for text in (
            "# furryp: foqa\nx = 1\n",
            "# furryp: foqa\nx = 1  # foqa:FUR102\n",
        ):
            with self.subTest(text=text):
                self.assertEqual(fixed(text), text)

    def test_non_enabled_codes_are_removed(self) -> None:
        """As ruff: ``--ignore FUR4 --fix`` removes the ``FUR4xx`` codes."""
        self.assert_fixes(
            [(f"{FLAGGED}  # foqa:FUR403\n", f"{FLAGGED}\n")], {"ignore": ["FUR4"]}
        )

    def test_text_after_a_removed_directive_goes_with_it(self) -> None:
        # As RUF100 of ruff 0.17.3 (checked); a comment after it stays (above).
        self.assert_fixes(
            [
                ("x = 1  # foqa bar\n", "x = 1\n"),
                ("x = 1  # foo # foqa bar\n", "x = 1  # foo\n"),
                ("x = 1  # foo # foqa:FUR102 bar\n", "x = 1  # foo\n"),
                ("x = 1  # a # foqa bar # b\n", "x = 1  # a\n"),
                ("x = 1  # foqa:FUR102,\n", "x = 1\n"),
                ("# foqa bar\nx = 1\n", "x = 1\n"),
            ]
        )

    def test_text_after_a_rewritten_directive_is_kept(self) -> None:
        # As RUF100 of ruff 0.17.3: `# noqa: F401 E501 bar` gives `# noqa: F401 bar`.
        self.assert_fixes(
            [
                (
                    f"{FLAGGED}  # foqa:FUR403 FUR102 bar\n",
                    f"{FLAGGED}  # foqa:FUR403 bar\n",
                ),
                (f"{FLAGGED}  # foqa:FUR403,FUR102,\n", f"{FLAGGED}  # foqa:FUR403,\n"),
                (f"{FLAGGED}  # foqa:FUR102,FUR403,\n", f"{FLAGGED}  # foqa:FUR403,\n"),
                (
                    f"{FLAGGED}  # foqa:FUR403 ,FUR102 # b\n",
                    f"{FLAGGED}  # foqa:FUR403 # b\n",
                ),
                (f"{FLAGGED}  # foqa:FUR403,,FUR102\n", f"{FLAGGED}  # foqa:FUR403\n"),
                (f"{FLAGGED}  # foqa:FUR403FUR102\n", f"{FLAGGED}  # foqa:FUR403\n"),
                (f"{FLAGGED}  # foqa:,FUR403,FUR102\n", f"{FLAGGED}  # foqa:FUR403\n"),
            ]
        )

    def test_a_comment_citing_foqa_is_not_touched(self) -> None:
        # Seen on a real project: the fix used to leave "# a bare ``".
        for text in (
            "x = 1  # a bare `# foqa`\n",
            "x = 1  # see `# foqa:FUR102`\n",
        ):
            with self.subTest(text=text):
                self.assertEqual(fixed(text), text)


if __name__ == "__main__":
    unittest.main()
