"""Selection of the rules of a file (SPEC §4.5)."""

import unittest
from pathlib import PurePosixPath

from furryp.config.selection import file_selection
from tests.support import (
    FLAGGED,
    PYPROJECT,
    TempDirTestCase,
    make_settings,
    real_registry,
    run_main,
    write_files,
)

FILE = PurePosixPath("pkg/module.py")
METRIC_RULES = ("FUR201", "FUR202", "FUR203")
DESIGN_RULES = ("FUR401", "FUR402", "FUR403", "FUR404")


def selection(data: dict[str, object], relative: PurePosixPath = FILE) -> set[str]:
    return set(file_selection(make_settings(data), real_registry(), relative))


class FileSelectionTest(unittest.TestCase):
    def test_default_selects_every_rule(self) -> None:
        self.assertEqual(
            selection({}),
            {
                "FUR000",
                "FUR001",
                "FUR101",
                "FUR102",
                *METRIC_RULES,
                *DESIGN_RULES,
            },
        )

    def test_prefix_code_and_name(self) -> None:
        self.assertEqual(
            selection({"select": ["FUR1"]}), {"FUR000", "FUR101", "FUR102"}
        )
        self.assertEqual(selection({"select": ["FUR403"]}), {"FUR000", "FUR403"})
        self.assertEqual(selection({"select": ["unused-foqa"]}), {"FUR000", "FUR001"})

    def test_extend_select(self) -> None:
        data = {"select": ["FUR1"], "extend-select": ["demeter-chain"]}
        self.assertEqual(selection(data), {"FUR000", "FUR101", "FUR102", "FUR403"})

    def test_ignore_always_wins(self) -> None:
        data = {"select": ["FUR403"], "extend-select": ["FUR1"], "ignore": ["FUR4"]}
        self.assertEqual(selection(data), {"FUR000", "FUR101", "FUR102"})

    def test_invalid_syntax_cannot_be_ignored(self) -> None:
        self.assertEqual(selection({"ignore": ["FUR"]}), {"FUR000"})
        self.assertEqual(selection({"ignore": ["invalid-syntax"]}), selection({}))
        data = {"per-file-ignores": {"pkg/**": ["FUR000"]}}
        self.assertIn("FUR000", selection(data))
        data = {"per-file-ignores": {"pkg/**": ["FUR"]}}
        self.assertEqual(selection(data), {"FUR000"})

    def test_per_file_ignores(self) -> None:
        data = {"per-file-ignores": {"pkg/**": ["FUR101"], "other.py": ["FUR102"]}}
        common = {"FUR000", "FUR001", *METRIC_RULES, *DESIGN_RULES}
        self.assertEqual(selection(data), {*common, "FUR102"})
        self.assertEqual(
            selection(data, PurePosixPath("other.py")), {*common, "FUR101"}
        )

    def test_per_file_ignores_match_parent_directories(self) -> None:
        for pattern in ("pkg", "pkg/*.py", "pkg/module.py"):
            with self.subTest(pattern=pattern):
                data = {"per-file-ignores": {pattern: ["FUR1"]}}
                self.assertNotIn("FUR102", selection(data))
        data = {"per-file-ignores": {"tests": ["FUR1"]}}
        self.assertIn("FUR102", selection(data))


class CliSelectionTest(TempDirTestCase):
    def test_cli_selection_applies(self) -> None:
        write_files(self.root, {PYPROJECT: "", "a.py": f"{FLAGGED}\n"})
        code, out, _ = run_main(["check", "--select", "FUR1"], self.root)
        self.assertEqual((code, out), (0, "All checks passed!\n"))
        code, out, _ = run_main(["check", "--ignore", "demeter-chain"], self.root)
        self.assertEqual((code, out), (0, "All checks passed!\n"))
        code, out, _ = run_main(["check", "--select", "FUR1,FUR40"], self.root)
        self.assertEqual(code, 1)
        self.assertIn("demeter-chain [FUR403]", out)


if __name__ == "__main__":
    unittest.main()
