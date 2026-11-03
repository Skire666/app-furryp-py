"""Cyclomatic complexity (SPEC FUR401): the values come from C901 of ruff 0.17.3."""

import ast
import unittest

from furryp.metrics.cyclomatic import cyclomatic_complexity


def complexity(text: str) -> int:
    """Return the complexity of the first function of ``text``."""
    node = ast.parse(text).body[0]
    assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    return cyclomatic_complexity(node)


class ComplexityTest(unittest.TestCase):
    def test_values_of_ruff(self) -> None:
        for expected, text in (
            (1, "def f():\n    pass\n"),
            (3, "def f(a):\n    if a: pass\n    elif a: pass\n    else: pass\n"),
            (1, "def f(a, b):\n    return (a and b) or (a if b else 0)\n"),
            (2, "def f(a):\n    for x in a: pass\n    else: pass\n"),
            (2, "def f(a):\n    while a: pass\n    else: pass\n"),
            (
                4,
                "def f(a):\n    try: pass\n    except ValueError: pass\n"
                "    except KeyError: pass\n    else: pass\n    finally: pass\n",
            ),
            (1, "def f(a):\n    try: pass\n    finally: pass\n"),
            (1, "def f(a):\n    with a: pass\n"),
            (1, "def f(a):\n    return [x for x in a if x]\n"),
            (1, "def f(a):\n    return lambda: 1 if a else 2\n"),
            (3, "def f(a):\n    def g():\n        if a: pass\n    return g\n"),
            (
                3,
                "def f(a):\n    match a:\n        case 1: pass\n        case 2: pass\n",
            ),
            (
                2,
                "def f(a):\n    match a:\n        case 1: pass\n        case _: pass\n",
            ),
            (
                2,
                "def f(a):\n    match a:\n        case 1: pass\n        case b: pass\n",
            ),
            (
                2,
                "def f(a):\n    match a:\n        case 1: pass\n"
                "        case 2 | _: pass\n",
            ),
            (
                2,
                "def f(a):\n    match a:\n        case 1: pass\n"
                "        case (_ as b) as c: pass\n",
            ),
            (
                3,
                "def f(a):\n    match a:\n        case 1: pass\n"
                "        case _ if a: pass\n",
            ),
            (1, "def f(a):\n    assert a\n"),
            (
                2,
                "async def f(a):\n    async for x in a: pass\n    async with a: pass\n",
            ),
            (
                3,
                "def f(a):\n    try: pass\n    except* ValueError: pass\n"
                "    except* KeyError: pass\n",
            ),
        ):
            with self.subTest(text=text):
                self.assertEqual(complexity(text), expected)

    def test_nested_blocks_all_count(self) -> None:
        text = (
            "def f(a):\n"
            "    for x in a:\n"
            "        while x:\n"
            "            try:\n"
            "                if x: pass\n"
            "            except E:\n"
            "                with x:\n"
            "                    if x: pass\n"
        )
        self.assertEqual(complexity(text), 6)

    def test_a_class_in_a_function_is_measured_apart(self) -> None:
        text = (
            "def f(a):\n"
            "    class C:\n"
            "        def m(self):\n"
            "            if a: pass\n"
            "    if a: pass\n"
        )
        self.assertEqual(complexity(text), 2)

    def test_a_deep_elif_chain_is_not_an_internal_error(self) -> None:
        branches = "".join(f"    elif a == {i}: pass\n" for i in range(3000))
        self.assertEqual(complexity(f"def f(a):\n    if a: pass\n{branches}"), 3002)


if __name__ == "__main__":
    unittest.main()
