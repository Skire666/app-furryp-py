"""FUR401 too-complex-class and FUR404 too-many-instance-attributes (SPEC §11)."""

import ast
import unittest

from furryp.metrics.classes import assigned_attributes, is_accessor
from furryp.metrics.file_metrics import FileMetrics
from tests.support import lint_text, make_settings, text_source


def measures(text: str) -> dict:
    """Return the measures of the classes of ``text``, by name."""
    return {item.name: item for item in FileMetrics(text_source(text)).classes}


def diagnostics(text: str, code: str, rule: str, option: str, value: int) -> list:
    """Return the diagnostics ``code`` of ``text``, with a lowered maximum."""
    settings = make_settings({"rules": {rule: {option: value}}})
    return [d for d in lint_text(text, settings).diagnostics if d.code == code]


def too_complex(text: str, limit: int = 1) -> list:
    return diagnostics(
        text, "FUR401", "too-complex-class", "max-class-complexity", limit
    )


def too_many(text: str, limit: int = 1) -> list:
    return diagnostics(
        text,
        "FUR404",
        "too-many-instance-attributes",
        "max-instance-attributes",
        limit,
    )


METHODS = "    def a(self):\n        if x: pass\n    def b(self):\n        pass\n"
METHOD_A = "def a(self): self.a = 1"
METHOD_B = "def b(self): self.b = 2"
UNDER_A_BLOCK = (
    ("if", f"class C:\n    if x:\n        {METHOD_A}\n        {METHOD_B}\n"),
    (
        "else",
        f"class C:\n    if x:\n        {METHOD_A}\n    else:\n        {METHOD_B}\n",
    ),
    (
        "elif",
        f"class C:\n    if x:\n        {METHOD_A}\n    elif y:\n        {METHOD_B}\n",
    ),
    (
        "try",
        f"class C:\n    try:\n        {METHOD_A}\n    except E:\n        {METHOD_B}\n",
    ),
    (
        "finally",
        f"class C:\n    try:\n        {METHOD_A}\n    finally:\n        {METHOD_B}\n",
    ),
    ("with", f"class C:\n    with x:\n        {METHOD_A}\n        {METHOD_B}\n"),
    ("for", f"class C:\n    for i in x:\n        {METHOD_A}\n        {METHOD_B}\n"),
    ("while", f"class C:\n    while x:\n        {METHOD_A}\n        {METHOD_B}\n"),
    (
        "match",
        f"class C:\n    match x:\n        case 1:\n            {METHOD_A}\n"
        f"        case _:\n            {METHOD_B}\n",
    ),
    (
        "nested blocks",
        f"class C:\n    if x:\n        try:\n            {METHOD_A}\n"
        f"        finally:\n            with y:\n                {METHOD_B}\n",
    ),
)
ATTRIBUTES = "    def run(self):\n        self.a = 1\n        self.b = 2\n"


class ComplexityTest(unittest.TestCase):
    def test_sum_of_the_methods(self) -> None:
        self.assertEqual(measures(f"class C:\n{METHODS}")["C"].complexity, 3)

    def test_every_function_of_the_body_counts(self) -> None:
        text = (
            "class C:\n"
            "    def __init__(self): pass\n"
            "    def __repr__(self): return ''\n"
            "    @staticmethod\n"
            "    def s(): pass\n"
            "    @classmethod\n"
            "    def k(cls): pass\n"
            "    @property\n"
            "    def p(self): return 1\n"
            "    @p.setter\n"
            "    def p(self, v): pass\n"
            "    async def t(self): pass\n"
        )
        self.assertEqual(measures(text)["C"].complexity, 7)

    def test_a_function_under_a_block_of_the_body_counts(self) -> None:
        for name, text in UNDER_A_BLOCK:
            with self.subTest(name=name):
                self.assertEqual(measures(text)["C"].complexity, 2)

    def test_both_sides_of_a_block_count(self) -> None:
        text = (
            "class C:\n"
            "    if x:\n        def m(self): pass\n"
            "    else:\n        def m(self): pass\n"
        )
        self.assertEqual(measures(text)["C"].complexity, 2)

    def test_deep_blocks_of_the_body_do_not_overflow(self) -> None:
        branches = "".join(
            f"    elif x == {i}:\n        def m{i}(self): pass\n" for i in range(3000)
        )
        text = f"class C:\n    if y:\n        pass\n{branches}"
        self.assertEqual(measures(text)["C"].complexity, 3000)

    def test_a_function_of_a_nested_class_under_a_block_counts_apart(self) -> None:
        text = (
            "class C:\n"
            "    if x:\n"
            "        class D:\n"
            "            def m(self): pass\n"
            "    def n(self): pass\n"
        )
        found = measures(text)
        self.assertEqual((found["C"].complexity, found["D"].complexity), (1, 1))

    def test_nested_functions_count_for_their_method(self) -> None:
        text = (
            "class C:\n"
            "    def m(self):\n"
            "        def g():\n"
            "            if x: pass\n"
            "        return g\n"
        )
        self.assertEqual(measures(text)["C"].complexity, 3)

    def test_a_lambda_adds_nothing_like_c901(self) -> None:
        text = "class C:\n    def m(self):\n        return lambda: 1 if x else 2\n"
        self.assertEqual(measures(text)["C"].complexity, 1)

    def test_a_nested_class_is_measured_apart(self) -> None:
        text = (
            "class Outer:\n"
            "    class Inner:\n"
            "        def m(self):\n"
            "            if x: pass\n"
            "    def n(self): pass\n"
        )
        found = measures(text)
        self.assertEqual(found["Outer"].complexity, 1)
        self.assertEqual(found["Inner"].complexity, 2)

    def test_a_class_in_a_method_is_measured_apart(self) -> None:
        text = (
            "class Outer:\n"
            "    def n(self):\n"
            "        class Local:\n"
            "            def m(self):\n"
            "                if x: pass\n"
        )
        found = measures(text)
        self.assertEqual(found["Outer"].complexity, 1)
        self.assertEqual(found["Local"].complexity, 2)

    def test_a_class_in_a_function_is_measured(self) -> None:
        text = "def f():\n    class Local:\n        def m(self): pass\n"
        self.assertEqual(measures(text)["Local"].complexity, 1)


class TooComplexClassTest(unittest.TestCase):
    def test_message_help_and_position(self) -> None:
        found = too_complex(f"class Report:\n{METHODS}", 2)
        self.assertEqual(len(found), 1)
        diagnostic = found[0]
        self.assertEqual(diagnostic.name, "too-complex-class")
        self.assertEqual(diagnostic.message, "Class `Report` is too complex (3 > 2)")
        self.assertEqual(
            diagnostic.help, "Move a group of related methods to a new class"
        )
        start, end = diagnostic.span.start, diagnostic.span.end
        self.assertEqual((start.line, start.column, end.column), (1, 7, 13))

    def test_the_maximum_is_strict(self) -> None:
        self.assertEqual(too_complex(f"class C:\n{METHODS}", 3), [])
        self.assertEqual(len(too_complex(f"class C:\n{METHODS}", 2)), 1)

    def test_default_maximum(self) -> None:
        methods = "".join(f"    def m{i}(self): pass\n" for i in range(80))
        settings = make_settings()
        codes = [
            d.code for d in lint_text(f"class C:\n{methods}", settings).diagnostics
        ]
        self.assertNotIn("FUR401", codes)
        more = f"class C:\n{methods}    def extra(self): pass\n"
        found = [d for d in lint_text(more, settings).diagnostics if d.code == "FUR401"]
        self.assertEqual(found[0].message, "Class `C` is too complex (81 > 80)")

    def test_a_decorated_class_points_at_its_name(self) -> None:
        span = too_complex(f"@deco\nclass C:\n{METHODS}")[0].span
        self.assertEqual((span.start.line, span.start.column), (2, 7))

    def test_a_non_ascii_name(self) -> None:
        span = too_complex(f"class Été:\n{METHODS}")[0].span
        self.assertEqual((span.start.column, span.end.column), (7, 10))

    def test_foqa_on_the_class_line(self) -> None:
        self.assertEqual(too_complex(f"class C:  # foqa:FUR401\n{METHODS}"), [])

    def test_test_classes_are_not_measured(self) -> None:
        for prelude, header in (
            ("import unittest\n", "class C(unittest.TestCase):"),
            ("from unittest import TestCase\n", "class C(TestCase):"),
            ("import unittest\n", "class C(unittest.IsolatedAsyncioTestCase):"),
            ("from django.test import SimpleTestCase\n", "class C(SimpleTestCase):"),
            ("", "class Test:"),
            ("", "class TestReport:"),
            ("", "class Test_report:"),
            ("", "class TestReport(Base):"),
        ):
            with self.subTest(header=header):
                self.assertEqual(too_complex(f"{prelude}{header}\n{METHODS}"), [])

    def test_what_is_not_a_test_class(self) -> None:
        init = "    def __init__(self): pass\n"
        for text in (
            f"class Tester:\n{METHODS}",
            f"class Testing:\n{METHODS}",
            f"class ReportTest:\n{METHODS}",
            f"class TestReport:\n{init}{METHODS}",
            f"class TestCase:\n{init}{METHODS}",
            f"class C(TestBase):\n{METHODS}",
        ):
            with self.subTest(text=text[:24]):
                self.assertEqual(len(too_complex(text)), 1)

    def test_dispatch_classes_are_not_measured(self) -> None:
        for prefix in ("visit_", "do_", "handle_", "on_"):
            with self.subTest(prefix=prefix):
                methods = "".join(
                    f"    def {name}(self): pass\n"
                    for name in (
                        f"{prefix}a",
                        f"{prefix}b",
                        f"{prefix}c",
                        "run",
                        "stop",
                        "reset",
                    )
                )
                self.assertEqual(too_complex(f"class C:\n{methods}"), [])

    def test_a_dispatch_class_counts_its_defs(self) -> None:
        pair = "    @property\n    def p(self): pass\n    @p.setter\n    def p(self, v): pass\n"
        visits = "".join(f"    def visit_{name}(self): pass\n" for name in "abc")
        self.assertTrue(measures(f"class C:\n{visits}{pair}")["C"].is_dispatch)
        other = pair.replace(" p(", " q(").replace("@p.", "@q.")
        self.assertFalse(measures(f"class C:\n{visits}{pair}{other}")["C"].is_dispatch)

    def test_a_dispatch_class_counts_the_defs_under_a_block(self) -> None:
        visits = "".join(f"        def visit_{name}(self): pass\n" for name in "abcde")
        self.assertTrue(measures(f"class C:\n    if x:\n{visits}")["C"].is_dispatch)

    def test_a_constructor_under_a_block_is_a_constructor(self) -> None:
        text = "class TestReport:\n    if x:\n        def __init__(self): pass\n"
        self.assertFalse(measures(text)["TestReport"].is_test)

    def test_a_method_under_a_block_keeps_a_class_from_being_data(self) -> None:
        text = "class C:\n    if x:\n        def run(self): print(1)\n"
        self.assertFalse(measures(text)["C"].is_data)

    def test_what_is_not_a_dispatch_class(self) -> None:
        for names in (
            ("visit_a", "visit_b", "visit_c", "visit_d"),
            ("visit_a", "visit_b", "run", "stop", "reset"),
            ("visit_a", "do_b", "handle_c", "on_d", "run", "stop"),
            ("visit", "visitor", "do", "a", "b"),
        ):
            with self.subTest(names=names):
                methods = "".join(f"    def {name}(self): pass\n" for name in names)
                self.assertEqual(len(too_complex(f"class C:\n{methods}")), 1)

    def test_a_data_class_is_measured_by_this_rule(self) -> None:
        text = f"import dataclasses\n@dataclasses.dataclass\nclass C:\n{METHODS}"
        self.assertEqual(len(too_complex(text)), 1)


class AssignedAttributesTest(unittest.TestCase):
    def assigned(self, body: str, signature: str = "self") -> set[str]:
        lines = "".join(f"        {line}\n" for line in body.split("\n"))
        text = f"class C:\n    def m({signature}):\n{lines}"
        node = ast.parse(text).body[0].body[0]
        return assigned_attributes(node)

    def test_every_form_of_assignment(self) -> None:
        for body, expected in (
            ("self.x = 1", {"x"}),
            ("self.x += 1", {"x"}),
            ("self.x: int = 1", {"x"}),
            ("self.x, self.y = 1, 2", {"x", "y"}),
            ("[self.x, *self.y] = z", {"x", "y"}),
            ("(self.x, (self.y, self.z)) = w", {"x", "y", "z"}),
            ("self.x = self.y = 1", {"x", "y"}),
            ("for self.x in y: pass", {"x"}),
            ("with y as self.x: pass", {"x"}),
            ("if y:\n    self.x = 1", {"x"}),
            ("try:\n    self.x = 1\nexcept E:\n    self.y = 2", {"x", "y"}),
        ):
            with self.subTest(body=body):
                self.assertEqual(self.assigned(body), expected)

    def test_what_is_not_an_assignment(self) -> None:
        for body in (
            "return self.x",
            "del self.x",
            "self.x: int",
            "self.x.y = 1",
            "self[0] = 1",
            "other.x = 1",
            "self.x()",
            "print(self.x)",
        ):
            with self.subTest(body=body):
                self.assertEqual(self.assigned(body), set())

    def test_nested_scopes(self) -> None:
        self.assertEqual(
            self.assigned("def g():\n    self.x = 1\nasync def h():\n    self.y = 2"),
            {"x", "y"},
        )
        self.assertEqual(
            self.assigned("f = lambda: [0 for self.x in y]"),
            {"x"},
        )

    def test_a_rebound_name_is_another_object(self) -> None:
        for body in (
            "def g(self):\n    self.x = 1",
            "def g(*self):\n    self.x = 1",
            "def g(*, self):\n    self.x = 1",
            "def g(**self):\n    self.x = 1",
            "class D:\n    def n(self):\n        self.x = 1",
            "f = lambda self: [0 for self.x in y]",
        ):
            with self.subTest(body=body):
                self.assertEqual(self.assigned(body), set())

    def test_a_local_class_may_reach_the_outer_instance(self) -> None:
        body = "class D:\n    def n(this):\n        self.x = 1\n        this.y = 2"
        self.assertEqual(self.assigned(body), {"x"})

    def test_the_first_parameter_may_have_any_name(self) -> None:
        self.assertEqual(self.assigned("this.x = 1", "this"), {"x"})
        self.assertEqual(self.assigned("me.x = 1", "me, /"), {"x"})
        self.assertEqual(self.assigned("other.x = 1", "self, other"), set())

    def test_without_parameter(self) -> None:
        self.assertEqual(self.assigned("self.x = 1", ""), set())
        self.assertEqual(self.assigned("self.x = 1", "*self"), set())


class InstanceAttributesTest(unittest.TestCase):
    def count(self, text: str) -> int:
        return measures(text)["C"].instance_attributes

    def test_distinct_names_in_all_the_methods(self) -> None:
        text = (
            "class C:\n"
            "    def __init__(self):\n        self.a = 1\n        self.b = 2\n"
            "    def m(self):\n        self.b = 3\n        self.c = 4\n"
            "    def n(this):\n        this.a = 5\n"
        )
        self.assertEqual(self.count(text), 3)

    def test_class_attributes_do_not_count(self) -> None:
        text = (
            "class C:\n"
            "    x = 1\n"
            "    y: int = 2\n"
            "    @classmethod\n"
            "    def k(cls):\n        cls.a = 1\n"
            "    def __new__(cls):\n        cls.b = 1\n"
            "    def __init_subclass__(cls):\n        cls.c = 1\n"
            "    def __class_getitem__(cls, item):\n        cls.d = 1\n"
        )
        self.assertEqual(self.count(text), 0)

    def test_a_static_method_has_no_instance(self) -> None:
        for decorator, prelude in (
            ("staticmethod", ""),
            ("abc.abstractstaticmethod", "import abc\n"),
            ("abc.abstractclassmethod", "import abc\n"),
        ):
            with self.subTest(decorator=decorator):
                text = (
                    f"{prelude}class C:\n"
                    f"    @{decorator}\n"
                    "    def s(other):\n        other.a = 1\n"
                )
                self.assertEqual(self.count(text), 0)

    def test_the_parents_do_not_count(self) -> None:
        text = (
            "class Base:\n"
            "    def __init__(self):\n        self.a = 1\n        self.b = 2\n"
            "class C(Base):\n"
            "    def __init__(self):\n        super().__init__()\n        self.c = 3\n"
        )
        self.assertEqual(self.count(text), 1)

    def test_a_nested_class_has_its_own_attributes(self) -> None:
        text = (
            "class C:\n"
            "    class Inner:\n"
            "        def __init__(self):\n            self.a = 1\n"
            "    def m(self):\n        self.b = 1\n"
        )
        self.assertEqual(self.count(text), 1)


class TooManyInstanceAttributesTest(unittest.TestCase):
    def test_a_method_under_a_block_of_the_body_counts(self) -> None:
        for name, text in UNDER_A_BLOCK:
            with self.subTest(name=name):
                self.assertEqual(measures(text)["C"].instance_attributes, 2)

    def test_message_help_and_position(self) -> None:
        text = (
            "class Order:\n"
            "    def __init__(self):\n        self.a = 1\n        self.b = 2\n"
            "    def run(self):\n        self.c = 3\n"
        )
        found = too_many(text, 2)
        self.assertEqual(len(found), 1)
        diagnostic = found[0]
        self.assertEqual(diagnostic.name, "too-many-instance-attributes")
        self.assertEqual(
            diagnostic.message, "Class `Order` has too many attributes (3 > 2)"
        )
        self.assertEqual(
            diagnostic.help,
            "Group the attributes that always go together in a separate object",
        )
        start, end = diagnostic.span.start, diagnostic.span.end
        self.assertEqual((start.line, start.column, end.column), (1, 7, 12))

    def test_the_maximum_is_strict(self) -> None:
        self.assertEqual(too_many(f"class C:\n{ATTRIBUTES}", 2), [])
        self.assertEqual(len(too_many(f"class C:\n{ATTRIBUTES}", 1)), 1)

    def test_default_maximum(self) -> None:
        attributes = "".join(f"        self.a{i} = 1\n" for i in range(20))
        text = f"class C:\n    def run(self):\n{attributes}"
        settings = make_settings()
        codes = [d.code for d in lint_text(text, settings).diagnostics]
        self.assertNotIn("FUR404", codes)
        more = text + "        self.extra = 1\n"
        found = [d for d in lint_text(more, settings).diagnostics if d.code == "FUR404"]
        self.assertEqual(
            found[0].message, "Class `C` has too many attributes (21 > 20)"
        )

    def test_known_data_classes_are_not_measured(self) -> None:
        for prelude, header in (
            ("import dataclasses\n", "@dataclasses.dataclass\nclass C:"),
            ("from dataclasses import dataclass\n", "@dataclass\nclass C:"),
            ("from dataclasses import dataclass as d\n", "@d(frozen=True)\nclass C:"),
            ("import attr\n", "@attr.s\nclass C:"),
            ("import attr\n", "@attr.s(auto_attribs=True)\nclass C:"),
            ("import attr\n", "@attr.attrs\nclass C:"),
            ("import attr\n", "@attr.attributes\nclass C:"),
            ("import attr\n", "@attr.define\nclass C:"),
            ("import attr\n", "@attr.frozen\nclass C:"),
            ("import attr\n", "@attr.mutable\nclass C:"),
            ("import attrs\n", "@attrs.define\nclass C:"),
            ("from attrs import frozen\n", "@frozen\nclass C:"),
            ("import attrs\n", "@attrs.mutable\nclass C:"),
            ("import pydantic\n", "@pydantic.dataclasses.dataclass\nclass C:"),
            ("import pydantic\n", "class C(pydantic.BaseModel):"),
            ("from pydantic import BaseModel\n", "class C(BaseModel):"),
            ("from pydantic import BaseModel\n", "class C(BaseModel[T], Other):"),
            ("from pydantic_settings import BaseSettings\n", "class C(BaseSettings):"),
            ("from typing import NamedTuple\n", "class C(NamedTuple):"),
            ("import typing\n", "class C(typing.TypedDict):"),
            ("from typing_extensions import TypedDict\n", "class C(TypedDict):"),
            ("from collections import namedtuple\n", "class C(namedtuple('B', 'x')):"),
            ("from enum import Enum\n", "class C(Enum):"),
            ("import enum\n", "class C(enum.IntEnum):"),
            ("import enum\n", "class C(enum.StrEnum):"),
            ("from enum import Flag\n", "class C(Flag):"),
            ("import enum\n", "class C(enum.IntFlag):"),
        ):
            with self.subTest(header=header):
                self.assertEqual(too_many(f"{prelude}{header}\n{ATTRIBUTES}"), [])

    def test_a_name_that_only_looks_known_is_measured(self) -> None:
        for prelude, header in (
            ("", "@dataclass\nclass C:"),
            ("from mine import dataclass\n", "@dataclass\nclass C:"),
            ("", "class C(BaseModel):"),
            ("from mine import BaseModel\n", "class C(BaseModel):"),
            ("", "class C(Enum):"),
        ):
            with self.subTest(prelude=prelude, header=header):
                self.assertEqual(len(too_many(f"{prelude}{header}\n{ATTRIBUTES}")), 1)

    def test_data_classes_by_their_methods_are_not_measured(self) -> None:
        for methods in (
            "",
            "    def __repr__(self):\n        return ''\n",
            "    def get_a(self):\n        return self.a\n",
            "    def a_value(self):\n        '''Doc.'''\n        return self.a\n",
            "    def set_a(self, value):\n        self.a = value\n",
            "    def set_b(self, value: int):\n        self.b: int = value\n",
            "    @property\n    def p(self):\n        return self.a\n",
            "    def __eq__(self, other):\n        return self.a == other.a\n",
        ):
            with self.subTest(methods=methods):
                text = (
                    "class C:\n"
                    "    def __init__(self):\n"
                    "        self.a = 1\n        self.b = 2\n"
                    f"{methods}"
                )
                self.assertEqual(too_many(text), [])

    def test_one_real_method_is_enough_to_measure_the_class(self) -> None:
        for body in (
            "return self.a + 1",
            "self.a = 1",
            "self.a = other",
            "return self.a.b",
            "return self.a()",
            "self.a = value\n        self.b = value",
            "pass",
        ):
            with self.subTest(body=body):
                text = (
                    "class C:\n"
                    "    def __init__(self):\n"
                    "        self.a = 1\n        self.b = 2\n"
                    f"    def m(self, value):\n        {body}\n"
                )
                self.assertEqual(len(too_many(text)), 1)

    def test_test_classes_are_not_measured(self) -> None:
        text = f"import unittest\nclass C(unittest.TestCase):\n{ATTRIBUTES}"
        self.assertEqual(too_many(text), [])
        self.assertEqual(too_many(f"class TestC:\n{ATTRIBUTES}"), [])

    def test_a_dispatch_class_is_measured_by_this_rule(self) -> None:
        names = ("visit_a", "visit_b", "visit_c", "run", "stop")
        methods = "".join(f"    def {name}(self): pass\n" for name in names)
        self.assertEqual(len(too_many(f"class C:\n{ATTRIBUTES}{methods}")), 1)

    def test_is_accessor_reads_the_body_not_the_name(self) -> None:
        text = (
            "class C:\n"
            "    def compute(self):\n        return self.a\n"
            "    def get_a(self):\n        return self.a + 1\n"
        )
        body = ast.parse(text).body[0].body
        self.assertTrue(is_accessor(body[0]))
        self.assertFalse(is_accessor(body[1]))


if __name__ == "__main__":
    unittest.main()
