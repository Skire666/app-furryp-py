"""Halstead metrics and the rules FUR201 and FUR202 (SPEC §11, A09, A13)."""

import unittest

from furryp.core.diagnostic import FILE_START
from furryp.metrics.file_metrics import FileMetrics
from furryp.metrics.halstead import Halstead, metric_value
from tests.support import codes_at, lint_text, make_settings, text_source


def metrics_of(text: str) -> FileMetrics:
    return FileMetrics(text_source(text))


def counts(halstead: Halstead) -> tuple[int, int, int, int]:
    return (
        halstead.distinct_operators,
        halstead.distinct_operands,
        halstead.total_operators,
        halstead.total_operands,
    )


def file_counts(text: str) -> tuple[int, int, int, int]:
    return counts(metrics_of(text).halstead)


def function_counts(text: str, index: int = 0) -> tuple[int, int, int, int]:
    return counts(metrics_of(text).functions[index].halstead)


def rule_settings(code: str, name: str, **options: object) -> object:
    return make_settings({"select": [code], "rules": {name: options}})


class FormulaTest(unittest.TestCase):
    def test_computed_by_hand(self) -> None:
        # def add ( a , b ) : return a + b — the closing ")" is not counted.
        # Operators: def ( , : return +     n1 = 6, N1 = 6
        # Operands: add a b a b             n2 = 3, N2 = 5
        halstead = metrics_of("def add(a, b):\n    return a + b\n").halstead
        self.assertEqual(counts(halstead), (6, 3, 6, 5))
        self.assertEqual((halstead.vocabulary, halstead.length), (9, 11))
        # 11 × log2(9) ; (6 / 2) × (5 / 3) ; 5 × 34.8691… ; 34.8691… / 3000
        self.assertAlmostEqual(halstead.volume, 34.8691750, places=6)
        self.assertAlmostEqual(halstead.difficulty, 5.0)
        self.assertAlmostEqual(halstead.effort, 174.3458751, places=6)
        self.assertAlmostEqual(halstead.bugs, 0.0116231, places=6)

    def test_metric_value(self) -> None:
        halstead = metrics_of("def add(a, b):\n    return a + b\n").halstead
        for metric in ("volume", "difficulty", "effort", "bugs"):
            with self.subTest(metric=metric):
                self.assertEqual(
                    metric_value(halstead, metric), getattr(halstead, metric)
                )

    def test_volume_is_zero_for_a_vocabulary_of_one_at_most(self) -> None:
        self.assertEqual(Halstead(0, 0, 0, 0).volume, 0.0)
        self.assertEqual(metrics_of("").halstead.volume, 0.0)
        self.assertEqual(metrics_of("pass\n").halstead.volume, 0.0)

    def test_volume_from_a_vocabulary_of_two(self) -> None:
        # Operator: ;. Operand: x, twice. 3 × log2(2) = 3
        self.assertEqual(metrics_of("x; x\n").halstead.volume, 3.0)

    def test_difficulty_is_zero_without_operands(self) -> None:
        self.assertEqual(metrics_of("pass\n").halstead.difficulty, 0.0)
        self.assertEqual(metrics_of("pass\n").halstead.effort, 0.0)


class TokenCountTest(unittest.TestCase):
    def test_hard_keywords_are_operators(self) -> None:
        # Operators: = None. Operands: x.
        self.assertEqual(file_counts("x = None\n"), (2, 1, 2, 1))

    def test_soft_keywords_are_operands(self) -> None:
        # Operators: = (4 times) True. Operands: case type _ match.
        self.assertEqual(file_counts("case = type = _ = match = True\n"), (2, 4, 5, 4))

    def test_closing_delimiters_are_not_counted(self) -> None:
        # Operators: = (3 times) ( [ {. Operands: x 1 y 2 z 3.
        self.assertEqual(file_counts("x = (1)\ny = [2]\nz = {3}\n"), (4, 6, 6, 6))

    def test_distinct_by_exact_text(self) -> None:
        self.assertEqual(file_counts("a = 1\nb = 1.0\n"), (1, 4, 2, 4))
        self.assertEqual(file_counts("a = 'x'\nb = \"x\"\n"), (1, 4, 2, 4))

    def test_not_significant_tokens_are_not_counted(self) -> None:
        self.assertEqual(file_counts("# comment\n\nx = 1  # c\n"), (1, 2, 1, 2))
        self.assertEqual(file_counts("if x:\n    y\n"), (2, 2, 2, 2))

    def test_docstrings_are_not_counted(self) -> None:
        # Operators: def ( :. Operand: f.
        self.assertEqual(
            file_counts('"""Doc."""\ndef f():\n    """Doc."""\n'), (3, 1, 3, 1)
        )
        self.assertEqual(file_counts('("doc")\nx = 1\n'), (1, 2, 1, 2))

    def test_token_after_a_non_ascii_docstring_is_counted(self) -> None:
        # Operators: ; =. Operands: x 1.
        self.assertEqual(file_counts('"""é"""; x = 1\n'), (2, 2, 2, 2))

    def test_f_strings(self) -> None:
        # Operators: = { !. Operands: x a y r b; quotes and "}" are not counted.
        self.assertEqual(file_counts('x = f"a{y!r}b"\n'), (3, 5, 3, 5))

    def test_t_strings(self) -> None:
        # Operators: = {. Operands: x a y b.
        self.assertEqual(file_counts('x = t"a{y}b"\n'), (2, 4, 2, 4))

    def test_empty_f_string_text_is_not_an_operand(self) -> None:
        # tokenize gives an empty FSTRING_MIDDLE after the nested format spec.
        # Operators: = { : { (distinct: = { :). Operands: x y > w.
        self.assertEqual(file_counts('x = f"{y:>{w}}"\n'), (3, 4, 4, 4))


class FunctionTokensTest(unittest.TestCase):
    TEXT = (
        "@deco\n"
        "def f(a):\n"
        '    """Doc."""\n'
        "    def g():\n"
        "        return a\n"
        "    return g\n"
    )

    def test_signature_and_nested_functions_are_included(self) -> None:
        # Operators: def ( : return, twice each. Operands: f a g a g.
        self.assertEqual(function_counts(self.TEXT), (4, 3, 8, 5))

    def test_nested_function_alone(self) -> None:
        # Operators: def ( : return. Operands: g a.
        self.assertEqual(function_counts(self.TEXT, 1), (4, 2, 4, 2))

    def test_async_keyword_is_included(self) -> None:
        # Operators: async def ( : pass. Operand: f.
        self.assertEqual(function_counts("async def f():\n    pass\n"), (5, 1, 5, 1))

    def test_end_of_a_function_with_non_ascii_text(self) -> None:
        # Operators: def ( : = ;, with = twice. Operands: f é 'é' ü 2.
        text = "def f(): é = 'é'; ü = 2\nx = 1\n"
        self.assertEqual(function_counts(text), (5, 5, 6, 5))


class HalsteadFileTest(unittest.TestCase):
    def diagnostics(self, text: str, **options: object) -> list[object]:
        settings = rule_settings("FUR201", "halstead-file", **options)
        return list(lint_text(text, settings).diagnostics)

    def test_message_position_and_help(self) -> None:
        text = "\ndef f(a):\n    return a\n"
        settings = rule_settings("FUR201", "halstead-file", max=0)
        report = lint_text(text, settings)
        self.assertEqual(codes_at(report), ["1:1 FUR201"])
        diagnostic = report.diagnostics[0]
        self.assertEqual(diagnostic.name, "halstead-file")
        # 7 × log2(6) = 18.09…
        self.assertEqual(
            diagnostic.message, "Halstead volume of the file is too high (18.1 > 0)"
        )
        self.assertEqual(diagnostic.span, FILE_START)
        self.assertEqual(
            diagnostic.help,
            "This file does a lot; consider splitting it or simplifying it",
        )

    def test_metric_option(self) -> None:
        # (4 / 2) × (3 / 2) = 3
        text = "def f(a):\n    return a\n"
        diagnostic = self.diagnostics(text, metric="difficulty", max=0)[0]
        self.assertEqual(
            diagnostic.message, "Halstead difficulty of the file is too high (3.0 > 0)"
        )

    def test_limit_is_exclusive(self) -> None:
        text = "def f(a):\n    return a\n"
        self.assertEqual(self.diagnostics(text, metric="difficulty", max=3), [])

    def test_default_limit(self) -> None:
        settings = make_settings({"select": ["FUR201"]})
        self.assertEqual(codes_at(lint_text("x = 1\n", settings)), [])
        names = "".join(f"x{index} = {index}\n" for index in range(500))
        self.assertEqual(codes_at(lint_text(names, settings)), [])
        names = "".join(f"x{index} = {index}\n" for index in range(510))
        self.assertEqual(codes_at(lint_text(names, settings)), ["1:1 FUR201"])


class HalsteadFunctionTest(unittest.TestCase):
    def diagnostics(self, text: str, **options: object) -> list[object]:
        settings = rule_settings("FUR202", "halstead-function", **options)
        return list(lint_text(text, settings).diagnostics)

    def test_message_position_and_help(self) -> None:
        text = (
            "class K:\n"
            "    def total(self, items):\n"
            "        total = 0\n"
            "        for item in items:\n"
            "            total += item.price\n"
            "            self.seen(item)\n"
            "        self.done(self, self)\n"
            "        return total\n"
        )
        settings = rule_settings("FUR202", "halstead-function", max=0)
        report = lint_text(text, settings)
        self.assertEqual(codes_at(report), ["2:9 FUR202"])
        diagnostic = report.diagnostics[0]
        self.assertEqual(diagnostic.name, "halstead-function")
        # 34 tokens, 10 operators + 8 operands; 34 × log2(18) = 141.8
        self.assertEqual(
            diagnostic.message,
            "Halstead volume of function `K.total` is too high (141.8 > 0)",
        )
        self.assertEqual(
            diagnostic.help,
            "This function does a lot; consider splitting it or simplifying it",
        )

    def test_nested_function_counts_in_its_parent_and_alone(self) -> None:
        text = "def outer():\n    def inner():\n        return 1\n    return inner\n"
        self.assertEqual(
            [d.message.split(" is too high")[0] for d in self.diagnostics(text, max=0)],
            [
                "Halstead volume of function `outer`",
                "Halstead volume of function `outer.inner`",
            ],
        )

    def test_metric_option_and_limit(self) -> None:
        text = "def f(a):\n    return a\n"
        self.assertEqual(
            self.diagnostics(text, metric="difficulty", max=2)[0].message,
            "Halstead difficulty of function `f` is too high (3.0 > 2)",
        )
        self.assertEqual(self.diagnostics(text, metric="difficulty", max=3), [])

    def test_default_limit(self) -> None:
        settings = make_settings({"select": ["FUR202"]})
        small = "def f(a):\n    return a\n"
        self.assertEqual(codes_at(lint_text(small, settings)), [])
        body = "".join(f"    x{index} = {index}\n" for index in range(58))
        self.assertEqual(
            codes_at(lint_text(f"def f():\n{body}", settings)), ["1:5 FUR202"]
        )


if __name__ == "__main__":
    unittest.main()
