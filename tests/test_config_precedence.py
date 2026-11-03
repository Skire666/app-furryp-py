"""Precedence: command line > furryp.json > defaults (SPEC §8.2, §8.4)."""

import unittest
from pathlib import Path

from furryp.config.loader import load_configuration
from furryp.config.options import ReportOptions, Settings, file_filter
from furryp.config.selection import CliSelection
from furryp.core.errors import UsageError
from furryp.core.registry import Registry
from tests.support import (
    CONFIG,
    PYPROJECT,
    LengthOptions,
    MetricOptions,
    NoOptions,
    NestedNames,
    TempDirTestCase,
    fake_registry,
    write_files,
)

SPEC_EXCLUDE = (
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    "*.egg-info",
)


class PrecedenceTest(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        write_files(self.root, {PYPROJECT: ""})

    def settings(
        self, content: str | None = None, cli: CliSelection | None = None
    ) -> Settings:
        explicit = None
        if content is not None:
            write_files(self.root, {CONFIG: content})
            explicit = Path(CONFIG)
        return load_configuration(self.root, explicit, fake_registry(), cli).settings

    def test_defaults_match_the_spec(self) -> None:
        configuration = load_configuration(self.root, None, Registry([]))
        self.assertIsNone(configuration.config_file)
        settings = configuration.settings
        self.assertEqual(settings, Settings())
        self.assertEqual(settings.include, ("**/*.py",))
        self.assertEqual(settings.exclude, SPEC_EXCLUDE)
        self.assertEqual(settings.extend_exclude, ())
        self.assertEqual(settings.select, ("FUR",))
        self.assertEqual((settings.extend_select, settings.ignore), ((), ()))
        self.assertEqual(settings.per_file_ignores, {})
        self.assertEqual(
            settings.report,
            ReportOptions(10, "furryp — audit", (0.20, 0.40, 0.60, 0.80)),
        )

    def test_every_rule_gets_its_default_options(self) -> None:
        self.assertEqual(
            self.settings("{}").rules,
            {
                "function-too-long": LengthOptions(),
                "halstead-file": MetricOptions(),
                "unused-foqa": NoOptions(),
            },
        )

    def test_file_overrides_defaults(self) -> None:
        settings = self.settings(
            '{"select": ["FUR1"], "exclude": ["a"], "report": {"top-n": 3}}'
        )
        self.assertEqual(settings.select, ("FUR1",))
        self.assertEqual(settings.exclude, ("a",))
        self.assertEqual(settings.report, ReportOptions(top_n=3))

    def test_extend_exclude_adds_to_exclude(self) -> None:
        settings = self.settings('{"extend-exclude": ["tests/fixtures"]}')
        self.assertEqual(
            file_filter(settings).exclude, SPEC_EXCLUDE + ("tests/fixtures",)
        )

    def test_cli_select_replaces_the_file_selection(self) -> None:
        cli = CliSelection(select=("FUR2",))
        self.assertEqual(self.settings('{"select": ["FUR1"]}', cli).select, ("FUR2",))

    def test_cli_without_select_keeps_the_file_selection(self) -> None:
        self.assertEqual(
            self.settings('{"select": ["FUR1"]}', CliSelection()).select, ("FUR1",)
        )

    def test_cli_extend_select_and_ignore_add_to_the_file(self) -> None:
        cli = CliSelection(extend_select=("FUR2",), ignore=("unused-foqa",))
        settings = self.settings(
            '{"extend-select": ["FUR1"], "ignore": ["FUR201"]}', cli
        )
        self.assertEqual(settings.extend_select, ("FUR1", "FUR2"))
        self.assertEqual(settings.ignore, ("FUR201", "unused-foqa"))

    def test_cli_unknown_selector_is_a_usage_error(self) -> None:
        with self.assertRaises(UsageError) as caught:
            self.settings(None, CliSelection(ignore=("FUR1", "XYZ")))
        self.assertEqual(
            str(caught.exception), '--ignore: unknown rule or prefix "XYZ"'
        )

    def test_partial_rule_options_are_merged_key_by_key(self) -> None:
        settings = self.settings('{"rules": {"function-too-long": {"max-lines": 30}}}')
        self.assertEqual(
            settings.rules["function-too-long"], LengthOptions(max_lines=30)
        )
        self.assertEqual(settings.rules["halstead-file"], MetricOptions())

    def test_lists_are_replaced_not_merged(self) -> None:
        settings = self.settings(
            '{"rules": {"function-too-long": {"exclude-methods": ["setup"]}}}'
        )
        self.assertEqual(
            settings.rules["function-too-long"].exclude_methods, ("setup",)
        )

    def test_free_key_objects_are_replaced(self) -> None:
        settings = self.settings(
            '{"rules": {"halstead-file": {"aliases": {"eff": "effort"}}}}'
        )
        self.assertEqual(settings.rules["halstead-file"].aliases, {"eff": "effort"})

    def test_nested_options_are_merged_key_by_key(self) -> None:
        settings = self.settings(
            '{"rules": {"halstead-file": {"names": {"second": "impl"}}}}'
        )
        self.assertEqual(
            settings.rules["halstead-file"].names, NestedNames("one", "impl")
        )

    def test_partial_report_keeps_other_defaults(self) -> None:
        settings = self.settings('{"report": {"title": "Mine"}}')
        self.assertEqual(settings.report, ReportOptions(title="Mine"))


if __name__ == "__main__":
    unittest.main()
