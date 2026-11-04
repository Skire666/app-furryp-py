"""End to end through ``python -m furryp`` in a subprocess (SPEC §4.4, §5.5, §5.7)."""

import json
import unittest
from pathlib import Path

from furryp.config.loader import load_configuration
from furryp.config.selection import CliSelection
from furryp.output.settings import render_settings
from tests.support import (
    CONFIG,
    FORBIDDEN_COMBINATIONS,
    PYPROJECT,
    TempDirTestCase,
    fake_registry,
    run_furryp,
    with_value,
    write_files,
)

ALL_PASSED = "All checks passed!\n"
NO_FILES = "warning: No Python files found under the given path(s)\n"


def split_settings(output: str) -> tuple[list[str], str]:
    """Split ``--show-settings`` output into its two header lines and its JSON."""
    lines = output.split("\n", 2)
    return lines[:2], lines[2]


class CheckTest(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        write_files(self.root, {PYPROJECT: ""})

    def test_check_python_files(self) -> None:
        write_files(self.root, {"pkg/a.py": "x = 1\n"})
        result = run_furryp(["check"], self.root)
        self.assertEqual(
            (result.returncode, result.stdout, result.stderr), (0, ALL_PASSED, "")
        )

    def test_no_python_files(self) -> None:
        write_files(self.root, {"docs/readme.txt": "x"})
        result = run_furryp(["check", "docs"], self.root)
        self.assertEqual(
            (result.returncode, result.stdout, result.stderr), (0, ALL_PASSED, NO_FILES)
        )

    def test_invalid_configuration(self) -> None:
        write_files(self.root, {CONFIG: '{"rules": {"file-too-lon": {}}}'})
        result = run_furryp(["check"], self.root)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(
            result.stderr,
            "error: furryp.json: rules.file-too-lon: unknown rule"
            ' (did you mean "file-too-long"?)\n',
        )

    def test_forbidden_combinations(self) -> None:
        for option, conflicts in FORBIDDEN_COMBINATIONS.items():
            for conflict in conflicts:
                with self.subTest(option=option, conflict=conflict):
                    result = run_furryp(
                        ["check", *with_value(conflict), *with_value(option)],
                        self.root,
                    )
                    self.assertEqual(
                        (result.returncode, result.stdout, result.stderr),
                        (2, "", f"error: {option} cannot be used with {conflict}\n"),
                    )

    def test_version(self) -> None:
        result = run_furryp(["--version"], self.root)
        self.assertEqual((result.returncode, result.stdout), (0, "furryp 1.0.2\n"))

    def test_output_stays_utf8_with_a_cp1252_environment(self) -> None:
        write_files(self.root, {CONFIG: '{"report": {"title": "Audit — équipe ☃"}}'})
        result = run_furryp(
            ["check", "--show-settings"], self.root, {"PYTHONIOENCODING": "cp1252"}
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"title": "Audit — équipe ☃"', result.stdout)


class ShowSettingsTest(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        write_files(self.root, {PYPROJECT: ""})

    def test_format_without_configuration_file(self) -> None:
        result = run_furryp(["check", "--show-settings"], self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        header, text = split_settings(result.stdout)
        self.assertEqual(
            header, [f"Project root: {self.root}", "Config file: (none, defaults)"]
        )
        data = json.loads(text)
        self.assertEqual(
            text, json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        )
        self.assertEqual(
            sorted(data),
            [
                "exclude",
                "extend-exclude",
                "extend-select",
                "ignore",
                "include",
                "per-file-ignores",
                "report",
                "rules",
                "select",
            ],
        )

    def test_output_is_reloadable_as_configuration(self) -> None:
        write_files(
            self.root, {CONFIG: '{"extend-exclude": ["gen"], "report": {"top-n": 4}}'}
        )
        first = run_furryp(["check", "--show-settings", "--ignore", "FUR"], self.root)
        self.assertEqual(first.returncode, 0, first.stderr)
        header, text = split_settings(first.stdout)
        self.assertEqual(header[1], f"Config file: {self.root / CONFIG}")
        self.assertEqual(json.loads(text)["ignore"], ["FUR"])
        write_files(self.root, {"saved/settings.json": text})
        second = run_furryp(
            ["check", "--show-settings", "--config", "saved/settings.json"], self.root
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(split_settings(second.stdout)[1], text)

    def test_rule_options_round_trip(self) -> None:
        registry = fake_registry()
        write_files(
            self.root, {CONFIG: '{"rules": {"halstead-file": {"metric": "effort"}}}'}
        )
        cli = CliSelection(select=("FUR1",), extend_select=("unused-foqa",))
        configuration = load_configuration(self.root, None, registry, cli)
        _, text = split_settings(render_settings(configuration))
        write_files(self.root, {"saved.json": text})
        reloaded = load_configuration(self.root, Path("saved.json"), registry)
        self.assertEqual(reloaded.settings, configuration.settings)
        self.assertEqual(
            json.loads(text)["rules"]["halstead-file"]["names"],
            {"first": "one", "second": "two"},
        )


if __name__ == "__main__":
    unittest.main()
