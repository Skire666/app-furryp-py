"""Lines of code (SPEC §10.1, §10.3) and FUR101 (§11)."""

import unittest

from furryp.metrics.file_metrics import FileMetrics
from tests.support import codes_at, lint_text, make_settings, text_source

SPEC_EXAMPLE = (
    "def f(x):\n"
    '    """Doc."""\n'
    "    # commentaire\n"
    "    y = x + 1\n"
    "    y = y * 2\n"
    "\n"
    "    z = call(y)\n"
    "    return z\n"
)
LOAD = (
    "def load(path):\n"
    "    result = []\n"
    "    for line in path:\n"
    "        if line:\n"
    "            result.append(line)\n"
    "        # comment\n"
    "        result.append(1)\n"
    "    if result:\n"
    "        return result\n"
    "    with path:\n"
    "        pass\n"
    "    return None\n"
)


def metrics_of(text: str) -> FileMetrics:
    return FileMetrics(text_source(text))


def too_long(text: str, max_lines: int = 0) -> list[str]:
    """Return the messages of FUR101 on ``text``."""
    settings = make_settings(
        {"select": ["FUR101"], "rules": {"function-too-long": {"max-lines": max_lines}}}
    )
    return [d.message for d in lint_text(text, settings).diagnostics]


class FileLinesTest(unittest.TestCase):
    def assert_code_lines(self, text: str, expected: int) -> None:
        self.assertEqual(metrics_of(text).code_lines, expected, text)

    def test_comments_and_blank_lines_are_not_code(self) -> None:
        self.assert_code_lines("# comment\n\nx = 1  # trailing\n\n# end\n", 1)

    def test_blank_line_inside_a_statement_is_not_code(self) -> None:
        self.assert_code_lines("x = [\n    1,\n\n    2,\n]\n", 4)

    def test_a_multi_line_token_covers_its_lines(self) -> None:
        self.assert_code_lines('x = """a\n\nb\n"""\n', 4)
        self.assert_code_lines('x = f"""a\n\n{y}\nb"""\n', 4)

    def test_docstrings_are_left_out(self) -> None:
        text = (
            '"""Module."""\n'
            "class K:\n"
            '    """Class\n\n    on three lines."""\n'
            "    def m(self):\n"
            '        """Method."""\n'
            "async def f():\n"
            '    """Function."""\n'
        )
        self.assert_code_lines(text, 3)

    def test_every_token_of_a_docstring_is_left_out(self) -> None:
        self.assert_code_lines('("doc")\nx = 1\n', 1)
        self.assert_code_lines('(\n    "doc"\n)\nx = 1\n', 1)
        self.assert_code_lines('"a" "b"\nx = 1\n', 1)

    def test_what_is_not_a_docstring(self) -> None:
        self.assert_code_lines('f"doc"\n', 1)
        self.assert_code_lines('b"doc"\n', 1)
        self.assert_code_lines('x = 1\n"doc"\n', 2)
        self.assert_code_lines('"doc"\n"second"\n', 1)

    def test_statement_after_a_non_ascii_docstring(self) -> None:
        self.assert_code_lines('"""é"""; x = 1\n', 1)

    def test_physical_lines(self) -> None:
        metrics = metrics_of("x = 1\r\ny = 2\rz = 3\n\n")
        self.assertEqual((metrics.lines, metrics.code_lines), (4, 3))
        metrics = metrics_of("x = '\f\v'\n")
        self.assertEqual((metrics.lines, metrics.code_lines), (1, 1))


class FunctionLinesTest(unittest.TestCase):
    def code_lines(self, text: str) -> list[tuple[str, int]]:
        return [(f.name, f.code_lines) for f in metrics_of(text).functions]

    def test_example_of_the_specification(self) -> None:
        self.assertEqual(self.code_lines(SPEC_EXAMPLE), [("f", 4)])
        self.assertEqual(
            too_long(SPEC_EXAMPLE, 3),
            ["Function `f` has too many lines of code (4 > 3)"],
        )
        self.assertEqual(too_long(SPEC_EXAMPLE, 4), [])

    def test_function_on_one_line(self) -> None:
        self.assertEqual(self.code_lines("def f(): return 1\n"), [("f", 1)])
        self.assertEqual(self.code_lines("def f(\n    a): return 1\n"), [("f", 1)])

    def test_signature_is_left_out(self) -> None:
        text = "def f(\n    a,\n    b,\n) -> int:\n    return a\n"
        self.assertEqual(self.code_lines(text), [("f", 1)])

    def test_decorators_are_left_out(self) -> None:
        text = "@first\n@second(\n    1,\n)\ndef f():\n    return 1\n"
        self.assertEqual(self.code_lines(text), [("f", 1)])

    def test_decorator_of_a_nested_function_counts_in_its_parent(self) -> None:
        text = "def f():\n    @d\n    def g():\n        return 1\n    return g\n"
        self.assertEqual(self.code_lines(text), [("f", 4), ("f.g", 1)])

    def test_docstring_alone(self) -> None:
        text = 'def f():\n    """Doc\n\n    on three lines."""\n'
        self.assertEqual(self.code_lines(text), [("f", 0)])

    def test_nested_function_counts_in_its_parent_and_alone(self) -> None:
        text = (
            "def outer():\n"
            "    def inner():\n"
            "        x = 1\n"
            "        return x\n"
            "    return inner\n"
        )
        self.assertEqual(
            too_long(text, 3), ["Function `outer` has too many lines of code (4 > 3)"]
        )
        self.assertEqual(
            too_long(text, 1),
            [
                "Function `outer` has too many lines of code (4 > 1)",
                "Function `outer.inner` has too many lines of code (2 > 1)",
            ],
        )

    def test_async_functions_and_methods(self) -> None:
        text = (
            "async def f():\n"
            "    return 1\n"
            "class K:\n"
            "    def m(self):\n"
            "        x = 1\n"
            "        return x\n"
        )
        self.assertEqual(self.code_lines(text), [("f", 1), ("K.m", 2)])


class FunctionTooLongTest(unittest.TestCase):
    def test_message_position_and_help(self) -> None:
        settings = make_settings(
            {"select": ["FUR101"], "rules": {"function-too-long": {"max-lines": 3}}}
        )
        report = lint_text(LOAD, settings)
        self.assertEqual(codes_at(report), ["1:5 FUR101"])
        diagnostic = report.diagnostics[0]
        self.assertEqual(diagnostic.name, "function-too-long")
        self.assertEqual(
            diagnostic.message, "Function `load` has too many lines of code (10 > 3)"
        )
        self.assertEqual((diagnostic.span.end.line, diagnostic.span.end.column), (1, 9))
        self.assertEqual(
            diagnostic.help,
            "Long functions are hard to read and test; consider splitting this one",
        )

    def test_default_limit(self) -> None:
        settings = make_settings({"select": ["FUR101"]})
        body = "    x = 1\n" * 26
        self.assertEqual(codes_at(lint_text(f"def f():\n{body}", settings)), [])
        self.assertEqual(
            codes_at(lint_text(f"def f():\n{body}    x = 2\n", settings)),
            ["1:5 FUR101"],
        )

    def test_position_is_the_name_in_characters(self) -> None:
        settings = make_settings(
            {"select": ["FUR101"], "rules": {"function-too-long": {"max-lines": 0}}}
        )
        text = "@d\nasync def f():\n    return 1\nclass É:\n    def m(self): return 1\n"
        self.assertEqual(
            codes_at(lint_text(text, settings)), ["2:11 FUR101", "5:9 FUR101"]
        )

    def test_qualified_names(self) -> None:
        text = "class Parser:\n    def load(self):\n        return 1\n"
        self.assertEqual(
            too_long(text),
            ["Function `Parser.load` has too many lines of code (1 > 0)"],
        )

    def test_directive_on_the_last_line_of_a_folded_signature(self) -> None:
        text = "def f(\n    a,\n):  # foqa:FUR101\n    return a\n"
        settings = make_settings(
            {
                "select": ["FUR", "FUR101"],
                "rules": {"function-too-long": {"max-lines": 0}},
            }
        )
        report = lint_text(text, settings)
        self.assertEqual(codes_at(report), [])
        self.assertEqual([d.code for d in report.suppressed], ["FUR101"])


if __name__ == "__main__":
    unittest.main()
