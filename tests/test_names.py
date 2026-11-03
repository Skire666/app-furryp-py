"""Resolution of imported names (SPEC §10.5) and AST accessors."""

import ast
import unittest
from pathlib import Path

from furryp.core.ast_utils import name_span, statement_span
from furryp.core.diagnostic import line_span
from furryp.core.names import import_table, is_type_checking_test
from tests.support import REPO_ROOT, text_source


def table(text: str) -> dict[str, str]:
    return dict(import_table(ast.parse(text)).targets)


def is_type_checking(text: str, imports: str = "") -> bool:
    test = ast.parse(text, mode="eval").body
    return is_type_checking_test(test, import_table(ast.parse(imports)))


class TypeCheckingTest(unittest.TestCase):
    """The forms ruff 0.17.3 recognizes (checked with TC004 and TC005)."""

    def test_recognized(self) -> None:
        for text, imports in (
            ("TYPE_CHECKING", ""),
            ("TYPE_CHECKING", "from other import TYPE_CHECKING"),
            ("typing.TYPE_CHECKING", "import typing"),
            ("t.TYPE_CHECKING", "import typing as t"),
            ("anything.TYPE_CHECKING", ""),
            ("TC", "from typing import TYPE_CHECKING as TC"),
            ("TC", "from typing_extensions import TYPE_CHECKING as TC"),
        ):
            with self.subTest(text=text, imports=imports):
                self.assertTrue(is_type_checking(text, imports))

    def test_not_recognized(self) -> None:
        for text, imports in (
            ("False", ""),
            ("0", ""),
            ("TC", ""),
            ("TC", "from other import TYPE_CHECKING as TC"),
            ("not TYPE_CHECKING", ""),
            ("typing.OTHER", "import typing"),
        ):
            with self.subTest(text=text, imports=imports):
                self.assertFalse(is_type_checking(text, imports))


class ImportTableTest(unittest.TestCase):
    def test_spec_examples(self) -> None:
        self.assertEqual(
            table("import enum\nimport enum as e\nfrom enum import Enum as E\n"),
            {"enum": "enum", "e": "enum", "E": "enum.Enum"},
        )

    def test_dotted_relative_and_star_imports(self) -> None:
        self.assertEqual(
            table(
                "import a.b.c\nimport a.b as ab\nfrom . import x\n"
                "from ..m import y as z\nfrom p import *\n"
            ),
            {"a": "a", "ab": "a.b", "x": ".x", "z": "..m.y"},
        )

    def test_module_scope_only_and_first_binding_wins(self) -> None:
        text = (
            "try:\n    from enum import StrEnum\n"
            "except ImportError:\n    from backports import StrEnum\n"
            "if True:\n    import os\n"
            "def f():\n    import json\n"
            "class C:\n    import io\n"
        )
        self.assertEqual(table(text), {"StrEnum": "enum.StrEnum", "os": "os"})

    def test_resolve(self) -> None:
        names = import_table(ast.parse("import enum as e\nfrom a import b\n"))
        expression = ast.parse("e.Enum.member", mode="eval").body
        self.assertEqual(names.resolve(expression), "enum.Enum.member")
        self.assertEqual(names.resolve(ast.parse("b", mode="eval").body), "a.b")
        self.assertEqual(names.resolve(ast.parse("x.y", mode="eval").body), "x.y")
        self.assertIsNone(names.resolve(ast.parse("f().y", mode="eval").body))
        self.assertEqual(names.target("e"), "enum")
        self.assertIsNone(names.target("x"))


class AstUtilsTest(unittest.TestCase):
    def test_spans_are_in_characters(self) -> None:
        source = text_source('x = "日本"; import os\nasync  def été(): pass\n')
        tree = source.tree
        assert tree is not None
        self.assertEqual(statement_span(source, tree.body[1]), line_span(1, 11, 20))
        definition = tree.body[2]
        assert isinstance(definition, ast.AsyncFunctionDef)
        self.assertEqual(name_span(source, definition), line_span(2, 12, 15))

    def test_statement_span_of_a_folded_statement(self) -> None:
        source = text_source("from a import (\n    b,\n)\n")
        tree = source.tree
        assert tree is not None
        self.assertEqual(statement_span(source, tree.body[0]), line_span(1, 1, 16))

    def test_name_span_of_a_decorated_class(self) -> None:
        source = text_source("@dataclass\nclass  Holder:\n    pass\n")
        tree = source.tree
        assert tree is not None
        definition = tree.body[0]
        assert isinstance(definition, ast.ClassDef)
        self.assertEqual(name_span(source, definition), line_span(2, 8, 14))

    def test_path_is_kept(self) -> None:
        self.assertEqual(text_source("x = 1\n").path, Path(REPO_ROOT / "example.py"))


if __name__ == "__main__":
    unittest.main()
