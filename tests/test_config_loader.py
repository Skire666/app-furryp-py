"""Discovery and reading of the configuration file (SPEC §3.1, §8.1)."""

import unittest
from pathlib import Path

from furryp.config.loader import find_configuration, load_configuration
from furryp.core.errors import ConfigError
from furryp.core.registry import Registry
from tests.support import (
    CONFIG,
    PYPROJECT,
    TempDirTestCase,
    fake_registry,
    write_files,
)

BOM = b"\xef\xbb\xbf"
NON_ASCII_CONFIG = (
    '{"report": {"title": "Audit — équipe ☃"}, "extend-exclude": ["données"]}'
)


class ReadingTest(TempDirTestCase):
    def test_bom_and_non_ascii(self) -> None:
        write_files(
            self.root, {PYPROJECT: "", CONFIG: BOM + NON_ASCII_CONFIG.encode("utf-8")}
        )
        settings = load_configuration(self.root, None, fake_registry()).settings
        self.assertEqual(settings.report.title, "Audit — équipe ☃")
        self.assertEqual(settings.extend_exclude, ("données",))

    def test_non_ascii_without_bom(self) -> None:
        write_files(self.root, {PYPROJECT: "", CONFIG: NON_ASCII_CONFIG})
        settings = load_configuration(self.root, None, fake_registry()).settings
        self.assertEqual(settings.report.title, "Audit — équipe ☃")

    def test_crlf_line_endings(self) -> None:
        write_files(
            self.root, {PYPROJECT: "", CONFIG: b'{\r\n  "select": ["FUR1"]\r\n}\r\n'}
        )
        settings = load_configuration(self.root, None, fake_registry()).settings
        self.assertEqual(settings.select, ("FUR1",))


class DiscoveryTest(TempDirTestCase):
    def test_root_is_the_closest_folder_with_pyproject(self) -> None:
        write_files(self.root, {PYPROJECT: "", CONFIG: "{}", "a/b/x.py": ""})
        cwd = self.root / "a" / "b"
        self.assertEqual(find_configuration(cwd, None), (self.root, self.root / CONFIG))

    def test_pyproject_without_furryp_json_uses_defaults(self) -> None:
        write_files(self.root, {PYPROJECT: "", "a/x.py": ""})
        configuration = load_configuration(self.root / "a", None, Registry([]))
        self.assertEqual(configuration.project_root, self.root)
        self.assertIsNone(configuration.config_file)

    def test_furryp_json_is_only_read_beside_pyproject(self) -> None:
        write_files(self.root, {PYPROJECT: "", "sub/furryp.json": '{"select": []}'})
        root, config_file = find_configuration(self.root / "sub", None)
        self.assertEqual(root, self.root)
        self.assertIsNone(config_file)

    def test_pyproject_content_is_not_read(self) -> None:
        write_files(self.root, {PYPROJECT: "not [valid toml", CONFIG: "{}"})
        configuration = load_configuration(self.root, None, Registry([]))
        self.assertEqual(configuration.config_file, self.root / CONFIG)

    def test_explicit_config_sets_the_root(self) -> None:
        write_files(self.root, {PYPROJECT: "", CONFIG: "{}", "other/conf.json": "{}"})
        root, config_file = find_configuration(self.root, Path("other/conf.json"))
        self.assertEqual(root, self.root / "other")
        self.assertEqual(config_file, self.root / "other" / "conf.json")

    def test_explicit_absolute_config(self) -> None:
        write_files(self.root, {"other/conf.json": "{}"})
        target = self.root / "other" / "conf.json"
        self.assertEqual(
            find_configuration(self.root / "x", target), (target.parent, target)
        )

    def test_explicit_config_missing_is_an_error(self) -> None:
        write_files(self.root, {PYPROJECT: ""})
        with self.assertRaises(ConfigError) as caught:
            load_configuration(self.root, Path("missing.json"), Registry([]))
        self.assertTrue(
            str(caught.exception).startswith("missing.json: cannot read file: ")
        )


if __name__ == "__main__":
    unittest.main()
