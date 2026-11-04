"""``FileMetrics``: shared, lazy, and the metric rules from the CLI (SPEC §9.2)."""

import unittest
from unittest import mock

from furryp.config.schema import SchemaError, dump_value
from furryp.metrics import lines
from furryp.metrics.file_metrics import FileMetrics
from tests.support import (
    CONFIG,
    PYPROJECT,
    TempDirTestCase,
    codes_at,
    lint_text,
    make_settings,
    run_furryp,
    text_source,
    write_files,
)

WALKED = """\
def first():
    def inner():
        class Local:
            def method(self):
                pass
        return Local
    return inner

class Outer:
    def method(self):
        pass

    class Inner:
        async def deep(self):
            pass

    if True:
        def conditional(self):
            pass

if True:
    def in_if():
        pass
else:
    def in_else():
        pass

try:
    def in_try():
        pass
except ImportError:
    def in_except():
        pass
finally:
    def in_finally():
        pass

with x:
    def in_with():
        pass

match x:
    case 1:
        def in_case():
            pass

for y in x:
    def in_for():
        pass
"""
EXPECTED_NAMES = [
    ("first", False),
    ("first.inner", True),
    ("first.inner.Local.method", True),
    ("Outer.method", False),
    ("Outer.Inner.deep", False),
    ("Outer.conditional", False),
    ("in_if", False),
    ("in_else", False),
    ("in_try", False),
    ("in_except", False),
    ("in_finally", False),
    ("in_with", False),
    ("in_case", False),
    ("in_for", False),
]
METRIC_CONFIG = """{
  "rules": {
    "function-too-long": {"max-lines": 1},
    "halstead-file": {"max": 10},
    "halstead-function": {"max": 10},
    "cognitive-complexity": {"max": 1}
  }
}"""
HEAVY = "def heavy(\n    a,\n    b,\n):\n    if a:\n        return b\n    return a\n"


class FileMetricsTest(unittest.TestCase):
    def test_names_and_order_of_the_functions(self) -> None:
        functions = FileMetrics(text_source(WALKED)).functions
        self.assertEqual([(f.name, f.nested) for f in functions], EXPECTED_NAMES)

    def test_span_of_a_function(self) -> None:
        function = FileMetrics(text_source("@d\ndef é():\n    pass\n")).functions[0]
        span = function.span
        self.assertEqual(
            (span.start.line, span.start.column, span.end.column), (2, 5, 6)
        )

    def test_lines_of_the_file(self) -> None:
        metrics = FileMetrics(text_source('"""Doc."""\n\nx = 1\n\n# end\n'))
        self.assertEqual((metrics.lines, metrics.code_lines), (5, 1))

    def test_measures_are_computed_once(self) -> None:
        metrics = FileMetrics(text_source("def f():\n    pass\n"))
        with mock.patch(
            "furryp.metrics.file_metrics.significant_tokens",
            wraps=lines.significant_tokens,
        ) as computed:
            first = metrics.functions
            self.assertIs(metrics.functions, first)
            self.assertIs(metrics.halstead, metrics.halstead)
            self.assertEqual(metrics.code_lines, 2)
        computed.assert_called_once()

    def test_a_source_that_does_not_parse_has_no_measure(self) -> None:
        metrics = FileMetrics(text_source("def f(:\n"))
        self.assertEqual(metrics.functions, ())
        self.assertEqual((metrics.lines, metrics.code_lines), (1, 0))


class OptionsTest(unittest.TestCase):
    def test_defaults_of_the_specification(self) -> None:
        rules = {
            name: dump_value(options) for name, options in make_settings().rules.items()
        }
        self.assertEqual(rules["function-too-long"], {"max-lines": 26})
        self.assertEqual(rules["halstead-file"], {"metric": "volume", "max": 15000})
        self.assertEqual(rules["halstead-function"], {"metric": "volume", "max": 1200})
        self.assertEqual(rules["cognitive-complexity"], {"max": 16})

    def test_invalid_options(self) -> None:
        cases = [
            (
                {"function-too-long": {"max-lines": -1}},
                "rules.function-too-long.max-lines: must be >= 0, got -1",
            ),
            (
                {"halstead-file": {"metric": "size"}},
                'rules.halstead-file.metric: must be one of "volume", "difficulty", '
                '"effort", "bugs", got "size"',
            ),
            (
                {"halstead-function": {"max": 1.5}},
                "rules.halstead-function.max: expected an integer, got number",
            ),
            (
                {"cognitive-complexity": {"maximum": 3}},
                'rules.cognitive-complexity.maximum: unknown key (did you mean "max"?)',
            ),
        ]
        for rules, message in cases:
            with self.subTest(message=message):
                with self.assertRaises(SchemaError) as caught:
                    make_settings({"rules": rules})
                self.assertEqual(str(caught.exception), message)


class SharedByTheRulesTest(unittest.TestCase):
    def computations(self, select: list[str]) -> int:
        settings = make_settings({"select": select})
        with mock.patch(
            "furryp.metrics.file_metrics.significant_tokens",
            wraps=lines.significant_tokens,
        ) as computed:
            lint_text("def f():\n    pass\n", settings)
        return computed.call_count

    def test_rules_share_the_measures_of_a_file(self) -> None:
        self.assertEqual(self.computations(["FUR101", "FUR2"]), 1)

    def test_nothing_is_computed_without_a_metric_rule(self) -> None:
        self.assertEqual(self.computations(["FUR102", "FUR403"]), 0)

    def test_metric_rules_do_not_run_on_invalid_syntax(self) -> None:
        settings = make_settings(
            {
                "select": ["FUR101", "FUR2"],
                "rules": {"halstead-file": {"max": 0}},
            }
        )
        self.assertEqual(codes_at(lint_text("x = (\n", settings)), ["1:5 FUR000"])


class MetricRulesCliTest(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        write_files(self.root, {PYPROJECT: "", CONFIG: METRIC_CONFIG, "a.py": HEAVY})

    def test_check_reports_each_rule(self) -> None:
        result = run_furryp(["check"], self.root)
        self.assertEqual(result.returncode, 1, result.stderr)
        for header in (
            "function-too-long [FUR101]: Function `heavy` has too many lines of code (3 > 1)",
            "halstead-file [FUR201]: Halstead volume of the file is too high (",
            "halstead-function [FUR202]: Halstead volume of function `heavy` is too high (",
            "cognitive-complexity [FUR203]: Cognitive complexity of function `heavy` is too high (3 > 1)",
        ):
            with self.subTest(header=header):
                self.assertIn(header, result.stdout)
        self.assertIn("Found 4 errors.", result.stdout)

    def test_statistics_lists_the_rules(self) -> None:
        result = run_furryp(["check", "--statistics"], self.root)
        self.assertEqual(result.returncode, 1, result.stderr)
        for line in (
            "1\tFUR101\tfunction-too-long",
            "1\tFUR201\thalstead-file",
            "1\tFUR202\thalstead-function",
            "1\tFUR203\tcognitive-complexity",
        ):
            with self.subTest(line=line):
                self.assertIn(line, result.stdout)

    def test_add_foqa_freezes_the_debt_at_the_right_scope(self) -> None:
        added = run_furryp(["check", "--add-foqa"], self.root)
        self.assertEqual(added.returncode, 0, added.stderr)
        self.assertEqual(
            (self.root / "a.py").read_bytes().decode("utf-8"),
            "# furryp: foqa:FUR201\n"
            "def heavy(\n"
            "    a,\n"
            "    b,\n"
            "):  # foqa:FUR101,FUR202,FUR203\n"
            "    if a:\n"
            "        return b\n"
            "    return a\n",
        )
        result = run_furryp(["check"], self.root)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_rule_documentation(self) -> None:
        for code in ("FUR101", "FUR201", "FUR202", "FUR203"):
            with self.subTest(code=code):
                result = run_furryp(["rule", code], self.root)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"({code})", result.stdout)


if __name__ == "__main__":
    unittest.main()
