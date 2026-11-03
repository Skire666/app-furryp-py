"""furryp passes its own rules with the configuration of the repository (§3, §13)."""

import unittest

from tests.support import (
    CONFIG,
    PYPROJECT,
    REPO_ROOT,
    TempDirTestCase,
    run_main,
    write_files,
)


class DogfoodingTest(unittest.TestCase):
    def test_furryp_checks_itself(self) -> None:
        self.assertEqual(
            run_main(["check", "furryp"], REPO_ROOT), (0, "All checks passed!\n", "")
        )


class LayerContractTest(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        config = (REPO_ROOT / CONFIG).read_text(encoding="utf-8")
        write_files(self.root, {PYPROJECT: "", CONFIG: config})

    def check(self, relative: str, text: str) -> tuple[int, str, str]:
        write_files(self.root, {relative: text})
        return run_main(["check", "--select", "FUR402", relative], self.root)

    def test_a_low_layer_cannot_import_a_high_one(self) -> None:
        code, stdout, _ = self.check("furryp/core/x.py", "from furryp.cli import app\n")
        self.assertEqual(code, 1)
        self.assertIn(
            "Import of `furryp.cli` breaks contract `furryp-layers`: "
            "`furryp.core` must not import `furryp.cli`",
            stdout,
        )

    def test_a_relative_import_is_resolved(self) -> None:
        code, stdout, _ = self.check("furryp/rules/x.py", "from ..lint import runner\n")
        self.assertEqual(code, 1)
        self.assertIn("`furryp.rules` must not import `furryp.lint`", stdout)

    def test_a_high_layer_can_import_a_low_one(self) -> None:
        code, stdout, _ = self.check("furryp/lint/x.py", "from furryp.core import x\n")
        self.assertEqual((code, stdout), (0, "All checks passed!\n"))

    def test_same_level_layers_can_import_each_other(self) -> None:
        code, _, _ = self.check("furryp/fix/x.py", "from furryp.output import x\n")
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
