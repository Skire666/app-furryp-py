"""Cognitive complexity and the rule FUR203 (SPEC §11, A12, A13)."""

import unittest

from furryp.metrics.file_metrics import FileMetrics, FunctionMetrics
from tests.support import codes_at, lint_text, make_settings, text_source

REFERENCE = """\
def sum_of_primes(limit):
    total = 0
    for i in range(2, limit):
        for j in range(2, i):
            if i % j == 0:
                break
        else:
            total += i
    return total

def classify(items, strict):
    result = []
    for item in items:
        if item.ok and (strict or item.forced):
            result.append(item)
        elif item.retry:
            result.append(item if strict else None)
    return [r for r in result if r]

def route(event):
    match event:
        case {"type": "click", "x": x} if x > 0:
            return handle(x)
        case Key(code=code):
            return code
        case _:
            return None
"""
HELP = "Branches and nesting make this function hard to follow; consider simplifying its control flow"


def functions_of(text: str) -> dict[str, FunctionMetrics]:
    return {f.name: f for f in FileMetrics(text_source(text)).functions}


def contributions(text: str, name: str = "f") -> list[tuple[str, int, int]]:
    return [
        (item.construct, item.line, item.points)
        for item in functions_of(text)[name].contributions
    ]


def score(text: str, name: str = "f") -> int:
    return functions_of(text)[name].cognitive


def in_function(*lines: str) -> str:
    """Return a function ``f`` whose body is ``lines``, from line 2."""
    return "\n".join(["def f():", *(f"    {line}" for line in lines), ""])


class ReferenceExamplesTest(unittest.TestCase):
    def test_totals(self) -> None:
        functions = functions_of(REFERENCE)
        self.assertEqual(
            {name: function.cognitive for name, function in functions.items()},
            {"sum_of_primes": 9, "classify": 10, "route": 5},
        )

    def test_contributions_of_sum_of_primes(self) -> None:
        self.assertEqual(
            contributions(REFERENCE, "sum_of_primes"),
            [
                ("for", 3, 1),
                ("for", 4, 2),
                ("if", 5, 3),
                ("break", 6, 1),
                ("else", 7, 1),
                ("return", 9, 1),
            ],
        )

    def test_contributions_of_classify(self) -> None:
        self.assertEqual(
            contributions(REFERENCE, "classify"),
            [
                ("for", 13, 1),
                ("if", 14, 2),
                ("boolean sequence", 14, 1),
                ("boolean sequence", 14, 1),
                ("elif", 16, 1),
                ("ternary", 17, 3),
                ("comprehension if", 18, 1),
            ],
        )

    def test_contributions_of_route(self) -> None:
        self.assertEqual(
            contributions(REFERENCE, "route"),
            [
                ("match", 21, 1),
                ("case guard", 22, 1),
                ("return", 23, 1),
                ("return", 25, 1),
                ("return", 27, 1),
            ],
        )

    def test_helps_and_messages(self) -> None:
        settings = make_settings(
            {"select": ["FUR203"], "rules": {"cognitive-complexity": {"max": 0}}}
        )
        report = lint_text(REFERENCE, settings)
        self.assertEqual(codes_at(report), ["11:5 FUR203", "1:5 FUR203", "20:5 FUR203"])
        self.assertEqual(
            [(d.name, d.message, d.help) for d in report.diagnostics],
            [
                (
                    "cognitive-complexity",
                    "Cognitive complexity of function `sum_of_primes` is too high (9 > 0)",
                    HELP,
                ),
                (
                    "cognitive-complexity",
                    "Cognitive complexity of function `classify` is too high (10 > 0)",
                    HELP,
                ),
                (
                    "cognitive-complexity",
                    "Cognitive complexity of function `route` is too high (5 > 0)",
                    HELP,
                ),
            ],
        )


class EachIncrementTest(unittest.TestCase):
    CASES: dict[str, tuple[str, list[tuple[str, int, int]]]] = {
        "if": (in_function("if a:", "    b()"), [("if", 2, 1)]),
        "ternary": (in_function("x = a if b else c"), [("ternary", 2, 1)]),
        "match, once": (
            in_function(
                "match a:", "    case 1:", "        b()", "    case 2:", "        c()"
            ),
            [("match", 2, 1)],
        ),
        "for": (in_function("for a in b:", "    c()"), [("for", 2, 1)]),
        "async for": (
            "async def f():\n    async for a in b:\n        c()\n",
            [("for", 2, 1)],
        ),
        "while": (in_function("while a:", "    b()"), [("while", 2, 1)]),
        "except": (
            in_function(
                "try:", "    a()", "except E:", "    b()", "except F:", "    c()"
            ),
            [("except", 4, 1), ("except", 6, 1)],
        ),
        "except*": (
            in_function("try:", "    a()", "except* E:", "    b()"),
            [("except", 4, 1)],
        ),
        "elif": (
            in_function("if a:", "    b()", "elif c:", "    d()"),
            [("if", 2, 1), ("elif", 4, 1)],
        ),
        "else of if": (
            in_function("if a:", "    b()", "else:", "    c()"),
            [("if", 2, 1), ("else", 4, 1)],
        ),
        "else of for": (
            in_function("for a in b:", "    c()", "else:", "    d()"),
            [("for", 2, 1), ("else", 4, 1)],
        ),
        "else of while": (
            in_function("while a:", "    b()", "else:", "    c()"),
            [("while", 2, 1), ("else", 4, 1)],
        ),
        "else of try": (
            in_function("try:", "    a()", "except E:", "    b()", "else:", "    c()"),
            [("except", 4, 1), ("else", 6, 1)],
        ),
        "boolean sequence": (
            in_function("x = a and b and c"),
            [("boolean sequence", 2, 1)],
        ),
        "boolean sequences of two operators": (
            in_function("x = a and b or c"),
            [("boolean sequence", 2, 1), ("boolean sequence", 2, 1)],
        ),
        "boolean operator nested in the same one": (
            in_function("x = a and (b and c)"),
            [("boolean sequence", 2, 1)],
        ),
        "boolean operator under another node": (
            in_function("x = a and not (b and c)"),
            [("boolean sequence", 2, 1), ("boolean sequence", 2, 1)],
        ),
        "case guard": (
            in_function("match a:", "    case b if c:", "        d()"),
            [("match", 2, 1), ("case guard", 3, 1)],
        ),
        "comprehension if": (
            in_function("x = [a for a in b if a if c]"),
            [("comprehension if", 2, 1), ("comprehension if", 2, 1)],
        ),
        "if of other comprehensions": (
            in_function(
                "x = {a for a in b if a}",
                "y = {a: a for a in b if a}",
                "z = (a for a in b if a)",
            ),
            [
                ("comprehension if", 2, 1),
                ("comprehension if", 3, 1),
                ("comprehension if", 4, 1),
            ],
        ),
        "try and finally": (
            in_function("try:", "    a()", "finally:", "    b()"),
            [("try", 2, 1), ("finally", 4, 1)],
        ),
        "with": (in_function("with a:", "    b()"), [("with", 2, 1)]),
        "async with": (
            "async def f():\n    async with a:\n        b()\n",
            [("with", 2, 1)],
        ),
        "break": (
            in_function("for a in b:", "    break"),
            [("for", 2, 1), ("break", 3, 1)],
        ),
        "continue": (
            in_function("for a in b:", "    continue"),
            [("for", 2, 1), ("continue", 3, 1)],
        ),
        "return": (in_function("return a"), [("return", 2, 1)]),
        "assert": (in_function("assert a"), [("assert", 2, 1)]),
        "pass": (in_function("pass"), [("pass", 2, 1)]),
        "walrus": (in_function("x = (y := 1)"), [("walrus", 2, 1)]),
        "several walruses": (
            in_function("x = (y := 1) + (z := 2)"),
            [("walrus", 2, 1), ("walrus", 2, 1)],
        ),
    }

    def test_each_increment_alone(self) -> None:
        for name, (text, expected) in self.CASES.items():
            with self.subTest(name):
                self.assertEqual(contributions(text), expected)

    def test_what_does_not_count(self) -> None:
        cases = {
            "raise": "raise E",
            "yield": "yield a",
            "del": "del a",
            "assignment": "x = 1",
            "annotated assignment": "x: int = 1",
            "augmented assignment": "x += 1",
            "call": "a()",
            "import": "import a",
            "global": "global a",
            "ellipsis": "...",
            "comprehension for": "x = [a for a in b]",
            "lambda": "x = lambda: a",
            "binary and compare": "x = a + b < c",
        }
        for name, line in cases.items():
            with self.subTest(name):
                self.assertEqual(contributions(in_function(line)), [])
        self.assertEqual(contributions("async def f():\n    await a\n"), [])
        self.assertEqual(contributions('def f():\n    """Doc."""\n'), [])


class NestingTest(unittest.TestCase):
    def test_structural_increments_pay_the_nesting(self) -> None:
        cases = {
            "if": ("if b:", "    c()"),
            "for": ("for b in c:", "    d()"),
            "while": ("while b:", "    c()"),
            "match": ("match b:", "    case 1:", "        c()"),
        }
        for name, inner in cases.items():
            with self.subTest(name):
                text = in_function("if a:", *(f"    {line}" for line in inner))
                self.assertEqual(contributions(text)[1][2], 2)

    def test_ternary_and_except_pay_the_nesting(self) -> None:
        self.assertEqual(
            contributions(in_function("if a:", "    x = b if c else d"))[1],
            ("ternary", 3, 2),
        )
        text = in_function(
            "if a:", "    try:", "        b()", "    except E:", "        c()"
        )
        self.assertEqual(contributions(text)[1], ("except", 5, 2))

    def test_other_increments_do_not_pay_the_nesting(self) -> None:
        cases = [
            (("elif c:", "    d()"), ("elif", 5, 1)),
            (("else:", "    d()"), ("else", 5, 1)),
        ]
        for clause, expected in cases:
            with self.subTest(clause=clause[0]):
                text = in_function(
                    "if a:",
                    "    if b:",
                    "        c()",
                    *(f"    {line}" for line in clause),
                )
                self.assertEqual(contributions(text)[-1], expected)
        deep = in_function("if a:", "    if b:", "        {}")
        for line, expected in (
            ("x = c and d", ("boolean sequence", 4, 1)),
            ("x = [c for c in d if c]", ("comprehension if", 4, 1)),
            (
                "match c:\n                case d if e:\n                    h()",
                ("case guard", 5, 1),
            ),
            ("return c", ("return", 4, 1)),
            ("break", ("break", 4, 1)),
            ("x = (c := d)", ("walrus", 4, 1)),
            ("pass", ("pass", 4, 1)),
            ("assert c", ("assert", 4, 1)),
        ):
            with self.subTest(line=line):
                self.assertIn(expected, contributions(deep.format(line)))

    def test_bodies_that_increase_the_nesting(self) -> None:
        inner = ("    if x:", "        y()")
        cases = {
            "if": ("if a:", *inner),
            "elif": ("if a:", "    b()", "elif c:", *inner),
            "else": ("if a:", "    b()", "else:", *inner),
            "for": ("for a in b:", *inner),
            "while": ("while a:", *inner),
            "else of a loop": ("for a in b:", "    c()", "else:", *inner),
            "except": ("try:", "    a()", "except E:", *inner),
            "else of a try": (
                "try:",
                "    a()",
                "except E:",
                "    b()",
                "else:",
                *inner,
            ),
            "case": ("match a:", "    case 1:", "    " + inner[0], "    " + inner[1]),
        }
        for name, lines in cases.items():
            with self.subTest(name):
                points = [
                    c[2] for c in contributions(in_function(*lines)) if c[0] == "if"
                ]
                self.assertEqual(points[-1], 2)

    def test_bodies_that_do_not_increase_the_nesting(self) -> None:
        inner = ("    if x:", "        y()")
        cases = {
            "try": ("try:", *inner, "finally:", "    z()"),
            "finally": ("try:", "    a()", "finally:", *inner),
            "with": ("with a:", *inner),
        }
        for name, lines in cases.items():
            with self.subTest(name):
                points = [
                    c[2] for c in contributions(in_function(*lines)) if c[0] == "if"
                ]
                self.assertEqual(points, [1])

    def test_expressions_of_a_header_keep_the_level_of_the_statement(self) -> None:
        self.assertEqual(
            contributions(in_function("if (a if b else c):", "    d()")),
            [("if", 2, 1), ("ternary", 2, 1)],
        )
        self.assertEqual(
            contributions(
                in_function("if a:", "    b()", "elif (c if d else e):", "    g()")
            ),
            [("if", 2, 1), ("elif", 4, 1), ("ternary", 4, 1)],
        )

    def test_operands_of_a_ternary_increase_the_nesting(self) -> None:
        for line in (
            "x = (a if b else c) if d else e",
            "x = a if (b if c else d) else e",
            "x = a if b else (c if d else e)",
        ):
            with self.subTest(line=line):
                self.assertEqual(
                    contributions(in_function(line)),
                    [("ternary", 2, 1), ("ternary", 2, 2)],
                )

    def test_lambda_increases_the_nesting(self) -> None:
        self.assertEqual(
            contributions(in_function("x = lambda: a if b else c")), [("ternary", 2, 2)]
        )

    def test_default_of_a_lambda_keeps_the_level(self) -> None:
        self.assertEqual(
            contributions(in_function("x = lambda p=(a if b else c): p")),
            [("ternary", 2, 1)],
        )


class NoCumulationTest(unittest.TestCase):
    def test_examples_of_the_specification(self) -> None:
        cases: dict[str, tuple[tuple[str, ...], list[tuple[str, int, int]]]] = {
            "return alone": (("return total",), [("return", 2, 1)]),
            "return and boolean": (("return a and b",), [("boolean sequence", 2, 1)]),
            "return and ternary": (("return x if c else y",), [("ternary", 2, 1)]),
            "if and walrus": (("if (m := g()):", "    a()"), [("if", 2, 1)]),
            "try, except, finally": (
                ("try:", "    a()", "except E:", "    b()", "finally:", "    c()"),
                [("except", 4, 1)],
            ),
            "try, finally": (
                ("try:", "    a()", "finally:", "    b()"),
                [("try", 2, 1), ("finally", 4, 1)],
            ),
            "with and walrus": (
                ("with (x := g()):", "    a()"),
                [("with", 2, 1), ("walrus", 2, 1)],
            ),
        }
        for name, (lines, expected) in cases.items():
            with self.subTest(name):
                self.assertEqual(contributions(in_function(*lines)), expected)

    def test_instruction_increments_do_not_cancel_each_other(self) -> None:
        self.assertEqual(
            contributions(in_function("return (x := 1)")),
            [("return", 2, 1), ("walrus", 2, 1)],
        )
        self.assertEqual(
            contributions(in_function("assert (x := 1)")),
            [("assert", 2, 1), ("walrus", 2, 1)],
        )

    def test_another_increment_of_the_statement_replaces_them(self) -> None:
        cases = [
            ("assert a or b", [("boolean sequence", 2, 1)]),
            ("return [r for r in x if r]", [("comprehension if", 2, 1)]),
            ("x = (y := 1) and z", [("boolean sequence", 2, 1)]),
            ("return (y := 1) if z else w", [("ternary", 2, 1)]),
            ("return lambda: a and b", [("boolean sequence", 2, 1)]),
        ]
        for line, expected in cases:
            with self.subTest(line=line):
                self.assertEqual(contributions(in_function(line)), expected)
        self.assertEqual(
            contributions(in_function("with a if b else c:", "    d()")),
            [("ternary", 2, 1)],
        )
        self.assertEqual(
            contributions(in_function("while (x := g()):", "    a()")),
            [("while", 2, 1)],
        )
        self.assertEqual(
            contributions(
                in_function("match (x := g()):", "    case 1:", "        a()")
            ),
            [("match", 2, 1)],
        )
        self.assertEqual(
            contributions(
                in_function("match a:", "    case b if (c := b):", "        d()")
            ),
            [("match", 2, 1), ("case guard", 3, 1)],
        )

    def test_nested_blocks_do_not_replace_them(self) -> None:
        self.assertEqual(
            contributions(in_function("with a:", "    return b and c")),
            [("with", 2, 1), ("boolean sequence", 3, 1)],
        )
        self.assertEqual(
            contributions(
                in_function("try:", "    x = a and b", "finally:", "    y = c or d")
            ),
            [
                ("try", 2, 1),
                ("boolean sequence", 3, 1),
                ("finally", 4, 1),
                ("boolean sequence", 5, 1),
            ],
        )

    def test_recursion_is_out_of_the_comparison(self) -> None:
        self.assertEqual(
            contributions(in_function("return f()")),
            [("return", 2, 1), ("recursion", 2, 1)],
        )


class ElifTest(unittest.TestCase):
    def test_elif(self) -> None:
        text = in_function("if a:", "    b()", "elif c:", "    d()")
        self.assertEqual(contributions(text), [("if", 2, 1), ("elif", 4, 1)])

    def test_else_with_an_if(self) -> None:
        text = in_function("if a:", "    b()", "else:", "    if c:", "        d()")
        self.assertEqual(
            contributions(text), [("if", 2, 1), ("else", 4, 1), ("if", 5, 2)]
        )

    def test_elif_chain_with_else(self) -> None:
        text = in_function(
            "if a:",
            "    b()",
            "elif c:",
            "    d()",
            "elif e:",
            "    h()",
            "else:",
            "    g()",
        )
        self.assertEqual(
            contributions(text),
            [("if", 2, 1), ("elif", 4, 1), ("elif", 6, 1), ("else", 8, 1)],
        )

    def test_elif_under_an_else(self) -> None:
        text = in_function(
            "if a:",
            "    b()",
            "else:",
            "    if c:",
            "        d()",
            "    elif e:",
            "        h()",
        )
        self.assertEqual(
            contributions(text),
            [("if", 2, 1), ("else", 4, 1), ("if", 5, 2), ("elif", 7, 1)],
        )

    def test_long_elif_chain(self) -> None:
        clauses = "".join(f"    elif a{i}:\n        b = {i}\n" for i in range(3000))
        text = f"def f():\n    if a:\n        b = 0\n{clauses}"
        self.assertEqual(score(text), 3001)
        self.assertEqual(
            codes_at(lint_text(text, make_settings({"select": ["FUR203"]}))),
            ["1:5 FUR203"],
        )


class ClauseLineTest(unittest.TestCase):
    def line_of(self, construct: str, text: str) -> int:
        return next(c[1] for c in contributions(text) if c[0] == construct)

    def test_comments_and_blank_lines_after_the_keyword(self) -> None:
        text = in_function("if a:", "    b()", "else:", "    # comment", "", "    c()")
        self.assertEqual(self.line_of("else", text), 4)
        text = in_function("try:", "    a()", "finally:", "    # comment", "    b()")
        self.assertEqual(self.line_of("finally", text), 4)

    def test_body_on_the_line_of_the_keyword(self) -> None:
        text = in_function("if a:", "    b()", "else: é = 'é'")
        self.assertEqual(self.line_of("else", text), 4)

    def test_ternaries_around_the_keyword(self) -> None:
        text = in_function(
            "if a:", "    x = b if c else d", "else:", "    y = e if f else g"
        )
        self.assertEqual(self.line_of("else", text), 4)

    def test_keyword_on_the_line_of_a_ternary(self) -> None:
        text = in_function("if a:", "    b()", "else: x = c if d else e")
        self.assertEqual(self.line_of("else", text), 4)

    def test_decorated_definition_after_the_keyword(self) -> None:
        text = in_function(
            "if a:",
            "    b()",
            "else:",
            "    @d(c if e else g)",
            "    def h():",
            "        i()",
        )
        self.assertEqual(self.line_of("else", text), 4)

    def test_else_of_a_loop_and_of_a_try(self) -> None:
        text = in_function("for a in b:", "    c()", "else:", "", "    d()")
        self.assertEqual(self.line_of("else", text), 4)
        text = in_function(
            "try:", "    a()", "except E:", "    b()", "else:", "    c()"
        )
        self.assertEqual(self.line_of("else", text), 6)


class RecursionTest(unittest.TestCase):
    def constructs(self, text: str, name: str) -> list[tuple[str, int, int]]:
        return [c for c in contributions(text, name) if c[0] == "recursion"]

    def test_function_calling_itself_counts_once(self) -> None:
        text = "def f(a):\n    x = f(a)\n    y = f(x)\n    return y\n"
        self.assertEqual(self.constructs(text, "f"), [("recursion", 2, 1)])

    def test_method_through_self_or_cls(self) -> None:
        for call in ("self.m()", "cls.m()"):
            with self.subTest(call=call):
                text = f"class K:\n    def m(self):\n        x = 1\n        {call}\n"
                self.assertEqual(self.constructs(text, "K.m"), [("recursion", 4, 1)])

    def test_bare_name_in_a_method_is_another_function(self) -> None:
        text = "class K:\n    def open(self):\n        open(self.path)\n"
        self.assertEqual(self.constructs(text, "K.open"), [])

    def test_receiver_in_a_function_is_not_a_recursion(self) -> None:
        text = "def f(self):\n    self.f()\n"
        self.assertEqual(self.constructs(text, "f"), [])

    def test_other_calls_are_not_a_recursion(self) -> None:
        for call in ("g()", "other.f()", "self.m.f()", "f"):
            with self.subTest(call=call):
                text = f"def f():\n    {call}\n"
                self.assertEqual(self.constructs(text, "f"), [])
        text = "class K:\n    def m(self):\n        other.m()\n        self.n()\n"
        self.assertEqual(self.constructs(text, "K.m"), [])

    def test_async_function(self) -> None:
        text = "async def f():\n    await f()\n"
        self.assertEqual(self.constructs(text, "f"), [("recursion", 2, 1)])

    def test_call_from_a_nested_function_counts_for_the_parent(self) -> None:
        text = "def f():\n    def g():\n        f()\n    g()\n"
        self.assertEqual(self.constructs(text, "f"), [("recursion", 3, 1)])

    def test_nested_function_calling_itself_is_not_its_parent(self) -> None:
        text = "def f():\n    def g():\n        g()\n    g()\n"
        self.assertEqual(self.constructs(text, "f"), [])


class NestedDefinitionsTest(unittest.TestCase):
    TEXT = (
        "def outer():\n"
        "    def inner():\n"
        "        if a:\n"
        "            b()\n"
        "    return inner\n"
    )

    def test_content_counts_in_the_parent(self) -> None:
        self.assertEqual(
            contributions(self.TEXT, "outer"), [("if", 3, 2), ("return", 5, 1)]
        )

    def test_nested_function_is_not_evaluated_alone(self) -> None:
        inner = functions_of(self.TEXT)["outer.inner"]
        self.assertTrue(inner.nested)
        self.assertEqual((inner.cognitive, inner.contributions), (0, ()))
        settings = make_settings(
            {"select": ["FUR203"], "rules": {"cognitive-complexity": {"max": 0}}}
        )
        self.assertEqual(codes_at(lint_text(self.TEXT, settings)), ["1:5 FUR203"])

    def test_class_in_a_function_increases_the_nesting(self) -> None:
        text = (
            "def f():\n"
            "    class K:\n"
            "        def m(self):\n"
            "            if a:\n"
            "                b()\n"
        )
        self.assertEqual(contributions(text), [("if", 4, 3)])
        self.assertTrue(functions_of(text)["f.K.m"].nested)

    def test_method_of_a_module_class_starts_at_level_zero(self) -> None:
        text = "class K:\n    def m(self):\n        if a:\n            b()\n"
        self.assertEqual(contributions(text, "K.m"), [("if", 3, 1)])

    def test_function_in_a_module_block_is_not_nested(self) -> None:
        text = "if a:\n    def f():\n        pass\n"
        self.assertEqual(contributions(text), [("pass", 3, 1)])

    def test_decorators_and_defaults_belong_to_the_enclosing_scope(self) -> None:
        text = (
            "def outer():\n"
            "    @d(a if b else c)\n"
            "    def inner(p=e if g else h, *, q=i or j):\n"
            "        pass\n"
        )
        self.assertEqual(
            contributions(text, "outer"),
            [
                ("ternary", 2, 1),
                ("ternary", 3, 1),
                ("boolean sequence", 3, 1),
                ("pass", 4, 1),
            ],
        )

    def test_a_function_has_no_decorator_and_default_of_its_own(self) -> None:
        text = "@d(a if b else c)\ndef f(p=e if g else h):\n    pass\n"
        self.assertEqual(contributions(text), [("pass", 3, 1)])

    def test_annotations_do_not_count(self) -> None:
        text = (
            "def f(p: (a if b else c)) -> (d if e else g):\n"
            "    def h(q: (a or b)) -> (c or d):\n"
            "        pass\n"
        )
        self.assertEqual(contributions(text), [("pass", 3, 1)])

    def test_bases_and_keywords_of_a_nested_class(self) -> None:
        text = "def f():\n    class K(a if b else c, metaclass=d or e):\n        pass\n"
        self.assertEqual(
            contributions(text),
            [("ternary", 2, 1), ("boolean sequence", 2, 1), ("pass", 3, 1)],
        )


class CognitiveComplexityTest(unittest.TestCase):
    def test_limit_is_exclusive(self) -> None:
        text = in_function("for a in b:", "    if c:", "        d()")
        for limit, expected in ((2, ["1:5 FUR203"]), (3, [])):
            with self.subTest(limit=limit):
                settings = make_settings(
                    {
                        "select": ["FUR203"],
                        "rules": {"cognitive-complexity": {"max": limit}},
                    }
                )
                self.assertEqual(codes_at(lint_text(text, settings)), expected)

    def test_default_limit(self) -> None:
        settings = make_settings({"select": ["FUR203"]})
        body = "    x = a and b\n" * 16
        self.assertEqual(codes_at(lint_text(f"def f():\n{body}", settings)), [])
        self.assertEqual(
            codes_at(lint_text(f"def f():\n{body}    y = c or d\n", settings)),
            ["1:5 FUR203"],
        )

    def test_qualified_name_and_position(self) -> None:
        settings = make_settings(
            {"select": ["FUR203"], "rules": {"cognitive-complexity": {"max": 0}}}
        )
        report = lint_text("class K:\n    def m(self):\n        pass\n", settings)
        self.assertEqual(codes_at(report), ["2:9 FUR203"])
        self.assertEqual(
            report.diagnostics[0].message,
            "Cognitive complexity of function `K.m` is too high (1 > 0)",
        )

    def test_very_long_expression(self) -> None:
        operands = " + ".join(["a"] * 20000)
        text = f"def f():\n    return {operands}\n"
        self.assertEqual(contributions(text), [("return", 2, 1)])


if __name__ == "__main__":
    unittest.main()
