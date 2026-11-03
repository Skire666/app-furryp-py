"""FUR001 unused-foqa, as ruff's RUF100: one diagnostic per directive (FUR001)."""

import unittest

from furryp.core.diagnostic import Diagnostic
from tests.support import FLAGGED, lint_text, make_settings

ALL = make_settings()
UNUSED_HELP = "Remove unused `foqa` directive"


def unused(text: str, data: dict[str, object] | None = None) -> list[str]:
    """FUR001 diagnostics of ``text``: ``LINE:COLUMN message``."""
    settings = ALL if data is None else make_settings(data)
    report = lint_text(text, settings)
    return [
        f"{d.span.start.line}:{d.span.start.column} {d.message}"
        for d in report.diagnostics
        if d.code == "FUR001"
    ]


def diagnostics(text: str) -> list[Diagnostic]:
    return [d for d in lint_text(text, ALL).diagnostics if d.code == "FUR001"]


class FileAndLineDirectivesTest(unittest.TestCase):
    """The forms compared with RUF100 of ruff 0.17.3."""

    CHAIN_AND_UNUSED = {"select": ["FUR403", "FUR001"]}

    def test_the_file_directive_wins_and_the_line_directive_is_unused(self) -> None:
        unused_line = "Unused `foqa` directive (unused: `FUR403`)"
        for text, expected in (
            (
                f"# furryp: foqa:FUR403\n{FLAGGED}  # foqa:FUR403\n",
                f"2:16 {unused_line}",
            ),
            (
                f"{FLAGGED}  # foqa:FUR403\n# furryp: foqa:FUR403\n",
                f"1:16 {unused_line}",
            ),
            (
                f"# furryp: foqa:FUR403\n{FLAGGED}  # foqa\n",
                "2:16 Unused blanket `foqa` directive",
            ),
            (
                f"{FLAGGED}  # foqa\n# furryp: foqa:FUR403\n",
                "1:16 Unused blanket `foqa` directive",
            ),
            (
                f"# furryp: foqa:FUR403\n{FLAGGED}  # foqa:FUR403,FUR102\n",
                "2:16 Unused `foqa` directive (unused: `FUR403`; non-enabled: `FUR102`)",
            ),
        ):
            with self.subTest(text=text):
                self.assertEqual(unused(text, self.CHAIN_AND_UNUSED), [expected])

    def test_a_line_directive_for_another_rule_still_serves(self) -> None:
        text = f"# furryp: foqa:FUR102\n{FLAGGED}  # foqa:FUR403\n"
        self.assertEqual(
            unused(text, self.CHAIN_AND_UNUSED),
            ["1:1 Unused `foqa` directive (non-enabled: `FUR102`)"],
        )

    def test_every_file_directive_that_names_the_rule_is_used(self) -> None:
        text = f"# furryp: foqa:FUR403\n# furryp: foqa:FUR403\n{FLAGGED}\n"
        self.assertEqual(unused(text, self.CHAIN_AND_UNUSED), [])

    def test_directives_that_serve_nothing_are_all_reported(self) -> None:
        self.assertEqual(
            unused(
                "# furryp: foqa:FUR403\nx = 1  # foqa:FUR403\n", self.CHAIN_AND_UNUSED
            ),
            [
                "1:1 Unused `foqa` directive (unused: `FUR403`)",
                "2:8 Unused `foqa` directive (unused: `FUR403`)",
            ],
        )

    def test_a_blanket_file_directive_exempts_the_whole_file(self) -> None:
        for text in (
            "# furryp: foqa\nx = 1\n",
            f"# furryp: foqa\n{FLAGGED}\n",
            f"# furryp: foqa\n{FLAGGED}  # foqa:FUR403\n",
            f"# furryp: foqa\n{FLAGGED}  # foqa\n",
            "# furryp: foqa\nx = 1  # foqa:FUR403\n",
            "# furryp: foqa\nx = 1  # foqa\n",
            "# furryp: foqa\n# furryp: foqa\nx = 1\n",
            "# furryp: foqa\n# furryp: foqa:FUR403\nx = 1\n",
            "# furryp: foqa:FUR403\n# furryp: foqa\nx = 1\n",
        ):
            with self.subTest(text=text):
                self.assertEqual(unused(text, self.CHAIN_AND_UNUSED), [])


class UnusedTest(unittest.TestCase):
    def test_used_directives_are_not_reported(self) -> None:
        self.assertEqual(unused(f"{FLAGGED}  # foqa:FUR403\n"), [])
        self.assertEqual(unused(f"{FLAGGED}  # foqa:demeter-chain\n"), [])
        self.assertEqual(unused(f"{FLAGGED}  # foqa\n"), [])
        self.assertEqual(unused(f"# furryp: foqa:FUR403\n{FLAGGED}\n"), [])

    def test_unused_codes(self) -> None:
        self.assertEqual(
            unused("x = 1  # foqa:FUR102,FUR403,FUR000\n"),
            ["1:8 Unused `foqa` directive (unused: `FUR102`, `FUR403`, `FUR000`)"],
        )

    def test_partially_used_directive(self) -> None:
        self.assertEqual(
            unused(f"{FLAGGED}  # foqa:FUR102,FUR403\n"),
            ["1:16 Unused `foqa` directive (unused: `FUR102`)"],
        )

    def test_unused_blanket(self) -> None:
        self.assertEqual(
            unused("x = 1  # foqa\n"), ["1:8 Unused blanket `foqa` directive"]
        )
        self.assertEqual(
            unused("x = 1  # foqa\n", {"select": ["FUR001"]}),
            ["1:8 Unused blanket `foqa` directive"],
        )

    def test_unused_file_directive(self) -> None:
        self.assertEqual(
            unused("# furryp: foqa:FUR102\nx = 1\n"),
            ["1:1 Unused `foqa` directive (unused: `FUR102`)"],
        )

    def test_unknown_identifiers_are_ignored(self) -> None:
        """As ruff, which ignores the codes it does not know."""
        self.assertEqual(unused("x = 1  # foqa:FUR999,no-such-rule\n"), [])
        self.assertEqual(unused(f"{FLAGGED}  # foqa:FUR403,FUR999\n"), [])
        self.assertEqual(
            unused("x = 1  # foqa:FUR102,FUR999\n"),
            ["1:8 Unused `foqa` directive (unused: `FUR102`)"],
        )

    def test_invalid_directive_is_not_reported(self) -> None:
        """As ruff: it gets a warning, and RUF100 does not see it."""
        for comment in (
            "# foqa.",
            "# foqa:",
            "# foqa: FUR102;",
            "# foqa. # foqa:FUR102",
        ):
            with self.subTest(comment=comment):
                self.assertEqual(unused(f"x = 1  {comment}\n"), [])

    def test_duplicated(self) -> None:
        self.assertEqual(
            unused(f"{FLAGGED}  # foqa:FUR403,FUR403\n"),
            ["1:16 Unused `foqa` directive (duplicated: `FUR403`)"],
        )
        self.assertEqual(
            unused(f"{FLAGGED}  # foqa:FUR403,demeter-chain\n"),
            ["1:16 Unused `foqa` directive (duplicated: `demeter-chain`)"],
        )
        self.assertEqual(
            unused("x = 1  # foqa:FUR999,FUR999\n"),
            ["1:8 Unused `foqa` directive (duplicated: `FUR999`)"],
        )

    def test_codes_of_rules_not_selected_are_non_enabled(self) -> None:
        """As ruff's RUF100, even when FUR001 is the only selected rule."""
        self.assertEqual(
            unused("x = 1  # foqa:FUR102,FUR403\n", {"select": ["FUR001"]}),
            ["1:8 Unused `foqa` directive (non-enabled: `FUR102`, `FUR403`)"],
        )
        self.assertEqual(
            unused("x = 1  # foqa:FUR403,FUR403\n", {"select": ["FUR001"]}),
            [
                (
                    "1:8 Unused `foqa` directive "
                    "(non-enabled: `FUR403`; duplicated: `FUR403`)"
                )
            ],
        )

    def test_per_file_ignores_make_codes_non_enabled(self) -> None:
        data = {"per-file-ignores": {"example.py": ["FUR403"]}}
        self.assertEqual(
            unused(f"{FLAGGED}  # foqa:FUR403\n", data),
            ["1:16 Unused `foqa` directive (non-enabled: `FUR403`)"],
        )

    def test_reasons_are_in_the_order_of_ruff(self) -> None:
        text = "x = 1  # foqa:FUR999,FUR403,FUR102,FUR403,FUR000\n"
        self.assertEqual(
            unused(text, {"ignore": ["FUR4"]}),
            [
                (
                    "1:8 Unused `foqa` directive (unused: `FUR102`, `FUR000`; "
                    "non-enabled: `FUR403`; duplicated: `FUR403`)"
                )
            ],
        )

    def test_not_selected(self) -> None:
        self.assertEqual(unused("x = 1  # foqa:FUR102\n", {"ignore": ["FUR001"]}), [])

    def test_not_evaluated_on_invalid_syntax(self) -> None:
        self.assertEqual(unused("x = (  # foqa:FUR102\n"), [])

    def test_cannot_be_suppressed(self) -> None:
        self.assertEqual(
            unused("# furryp: foqa:FUR001\nx = 1  # foqa:FUR102,FUR001\n"),
            [
                "1:1 Unused `foqa` directive (unused: `FUR001`)",
                "2:8 Unused `foqa` directive (unused: `FUR102`, `FUR001`)",
            ],
        )

    def test_help(self) -> None:
        for text in (
            "x = 1  # foqa:FUR102",
            "x = 1  # foqa",
            "x = 1  # foqa:FUR9,FUR9",
        ):
            with self.subTest(text=text):
                found = diagnostics(text + "\n")
                self.assertEqual([d.help for d in found], [UNUSED_HELP])


if __name__ == "__main__":
    unittest.main()
