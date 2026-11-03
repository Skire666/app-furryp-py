"""Strict validation of furryp.json, one test per kind of error (SPEC §8.3)."""

import json
import unittest
from pathlib import Path

from furryp.config.loader import load_configuration
from furryp.config.schema import json_key
from furryp.core.errors import ConfigError
from furryp.core.registry import Registry
from furryp.rules import ALL_RULES
from tests.support import CONFIG, TempDirTestCase, fake_registry, write_files


class ValidationTest(TempDirTestCase):
    def load(self, content: str | bytes, registry: Registry | None = None) -> None:
        write_files(self.root, {CONFIG: content})
        load_configuration(self.root, Path(CONFIG), registry or fake_registry())

    def assertError(self, content: str | bytes, expected: str) -> None:
        with self.assertRaises(ConfigError) as caught:
            self.load(content)
        self.assertEqual(str(caught.exception), f"{CONFIG}: {expected}")

    def assertErrorStartsWith(self, content: str, expected: str) -> None:
        with self.assertRaises(ConfigError) as caught:
            self.load(content)
        self.assertTrue(
            str(caught.exception).startswith(f"{CONFIG}: {expected}"), caught.exception
        )

    # --- file and JSON level ------------------------------------------------

    def test_invalid_json(self) -> None:
        self.assertErrorStartsWith(
            '{"select": [}', "invalid JSON: Expecting value: line 1"
        )

    def test_empty_file(self) -> None:
        self.assertErrorStartsWith("", "invalid JSON: Expecting value")

    def test_not_utf8(self) -> None:
        self.assertError(b'{"report": {"title": "\xe9"}}', "file is not valid UTF-8")

    def test_duplicate_key(self) -> None:
        self.assertError(
            '{"select": [], "select": ["FUR"]}', 'invalid JSON: duplicate key "select"'
        )

    def test_nan_is_refused(self) -> None:
        self.assertError(
            '{"report": {"top-n": NaN}}', "invalid JSON: NaN is not allowed"
        )

    def test_root_must_be_an_object(self) -> None:
        self.assertError("[]", "expected an object, got array")

    # --- keys ---------------------------------------------------------------

    def test_unknown_key_with_suggestion(self) -> None:
        self.assertError(
            '{"exclud": []}', 'exclud: unknown key (did you mean "exclude"?)'
        )

    def test_unknown_key_suggestion_ignores_case(self) -> None:
        self.assertError(
            '{"Exclude": []}', 'Exclude: unknown key (did you mean "exclude"?)'
        )

    def test_unknown_key_without_suggestion(self) -> None:
        self.assertError('{"zzz": 1}', "zzz: unknown key")

    def test_unknown_nested_key(self) -> None:
        self.assertError(
            '{"report": {"top_n": 1}}',
            'report.top_n: unknown key (did you mean "top-n"?)',
        )

    # --- types --------------------------------------------------------------

    def test_list_expected(self) -> None:
        self.assertError(
            '{"include": "**/*.py"}', "include: expected an array, got string"
        )

    def test_list_item_type(self) -> None:
        self.assertError(
            '{"exclude": ["a", 3]}', "exclude[1]: expected a string, got integer"
        )

    def test_object_expected(self) -> None:
        self.assertError(
            '{"per-file-ignores": []}',
            "per-file-ignores: expected an object, got array",
        )

    def test_object_value_item_type(self) -> None:
        self.assertError(
            '{"per-file-ignores": {"tests/**": [1]}}',
            "per-file-ignores.tests/**[0]: expected a string, got integer",
        )

    def test_nested_object_expected(self) -> None:
        self.assertError('{"report": 3}', "report: expected an object, got integer")

    def test_boolean_is_not_an_integer(self) -> None:
        self.assertError(
            '{"report": {"top-n": true}}',
            "report.top-n: expected an integer, got boolean",
        )

    def test_number_is_not_an_integer(self) -> None:
        self.assertError(
            '{"report": {"top-n": 2.5}}',
            "report.top-n: expected an integer, got number",
        )

    def test_null_is_refused(self) -> None:
        self.assertError(
            '{"report": {"title": null}}', "report.title: expected a string, got null"
        )

    def test_string_expected(self) -> None:
        self.assertError(
            '{"report": {"title": 3}}', "report.title: expected a string, got integer"
        )

    def test_number_expected(self) -> None:
        self.assertError(
            '{"report": {"rating-thresholds": ["a", 0.1, 0.2, 0.3]}}',
            "report.rating-thresholds[0]: expected a number, got string",
        )

    # --- domains ------------------------------------------------------------

    def test_negative_integer(self) -> None:
        self.assertError(
            '{"report": {"top-n": -1}}', "report.top-n: must be >= 0, got -1"
        )

    def test_rating_thresholds_domain(self) -> None:
        problem = (
            "report.rating-thresholds: "
            "expected 4 strictly increasing numbers between 0 and 1"
        )
        for value in (
            "[0.1, 0.2]",
            "[0.3, 0.2, 0.4, 0.5]",
            "[0, 0.05, 0.05, 0.2]",
            "[0, 0.5, 0.9, 1.5]",
            "[-0.1, 0, 0.5, 1]",
        ):
            with self.subTest(value=value):
                self.assertError(
                    f'{{"report": {{"rating-thresholds": {value}}}}}', problem
                )

    def test_rating_thresholds_accepts_integers(self) -> None:
        self.load('{"report": {"rating-thresholds": [0, 0.25, 0.5, 1]}}')

    # --- rules --------------------------------------------------------------

    def test_rules_must_be_an_object(self) -> None:
        self.assertError('{"rules": []}', "rules: expected an object, got array")

    def test_unknown_rule_with_suggestion(self) -> None:
        self.assertError(
            '{"rules": {"function-too-lon": {}}}',
            'rules.function-too-lon: unknown rule (did you mean "function-too-long"?)',
        )

    def test_rule_code_is_not_a_key(self) -> None:
        self.assertError(
            '{"rules": {"FUR101": {}}}',
            'rules.FUR101: unknown rule (did you mean "function-too-long"?)',
        )

    def test_rules_are_validated_against_the_real_registry(self) -> None:
        with self.assertRaises(ConfigError) as caught:
            self.load('{"rules": {"zzz": {}}}', Registry(ALL_RULES))
        self.assertEqual(str(caught.exception), f"{CONFIG}: rules.zzz: unknown rule")

    def test_rule_options_must_be_an_object(self) -> None:
        self.assertError(
            '{"rules": {"function-too-long": 3}}',
            "rules.function-too-long: expected an object, got integer",
        )

    def test_unknown_rule_option_with_suggestion(self) -> None:
        self.assertError(
            '{"rules": {"function-too-long": {"max_lines": 30}}}',
            'rules.function-too-long.max_lines: unknown key (did you mean "max-lines"?)',
        )

    def test_rule_option_type(self) -> None:
        self.assertError(
            '{"rules": {"function-too-long": {"count-blank-lines": "yes"}}}',
            "rules.function-too-long.count-blank-lines: expected a boolean, got string",
        )

    def test_rule_option_literal_domain(self) -> None:
        self.assertError(
            '{"rules": {"halstead-file": {"metric": "size"}}}',
            'rules.halstead-file.metric: must be one of "volume", "difficulty", '
            '"effort", "bugs", got "size"',
        )

    def test_rule_nested_option(self) -> None:
        self.assertError(
            '{"rules": {"halstead-file": {"names": {"third": "x"}}}}',
            "rules.halstead-file.names.third: unknown key",
        )

    # --- selectors ----------------------------------------------------------

    def test_unknown_selector(self) -> None:
        self.assertError(
            '{"select": ["FUR1", "XYZ"]}', 'select[1]: unknown rule or prefix "XYZ"'
        )

    def test_unknown_selector_with_suggestion(self) -> None:
        self.assertError(
            '{"ignore": ["function-too-lng"]}',
            'ignore[0]: unknown rule or prefix "function-too-lng" (did you mean "function-too-long"?)',
        )

    def test_selector_suggestion_ignores_case(self) -> None:
        self.assertError(
            '{"select": ["fur101"]}',
            'select[0]: unknown rule or prefix "fur101" (did you mean "FUR101"?)',
        )

    def test_family_prefix_is_suggested(self) -> None:
        self.assertError(
            '{"select": ["fur10"]}',
            'select[0]: unknown rule or prefix "fur10" (did you mean "FUR10"?)',
        )

    def test_prefix_matching_no_rule(self) -> None:
        self.assertErrorStartsWith(
            '{"extend-select": ["FUR9"]}',
            'extend-select[0]: unknown rule or prefix "FUR9"',
        )

    def test_unknown_selector_in_per_file_ignores(self) -> None:
        self.assertError(
            '{"per-file-ignores": {"tests/**": ["FUR101", "XYZ"]}}',
            'per-file-ignores.tests/**[1]: unknown rule or prefix "XYZ"',
        )

    def test_valid_selectors(self) -> None:
        self.load(
            '{"select": ["FUR", "FUR1", "FUR10", "FUR101", "halstead-file"],'
            ' "per-file-ignores": {"tests/**": ["unused-foqa"]}}'
        )

    def test_all_rules_prefix_is_valid_with_an_empty_registry(self) -> None:
        self.load('{"select": ["FUR"], "ignore": ["FUR"]}', Registry([]))


class JsonKeyTest(TempDirTestCase):
    def test_json_key(self) -> None:
        self.assertEqual(json_key("max_lines"), "max-lines")


if __name__ == "__main__":
    unittest.main()
