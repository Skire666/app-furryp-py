"""FUR403: chains of attributes, exemptions, message and help (SPEC §11)."""

import ast
import unittest

from furryp.rules.design import maximal_chains
from tests.support import lint_text, make_settings


def chains_of(text: str, count_calls: bool = False) -> set[tuple[str, int]]:
    """Return the chains of ``text`` as ``(root, attributes)``."""
    return {
        (ast.unparse(chain.root), chain.attributes)
        for chain in maximal_chains(ast.parse(text), count_calls)
    }


def chain_diagnostics(text: str, **options: object) -> list:
    """Return the FUR403 diagnostics of ``text`` with the given rule options."""
    data = {key.replace("_", "-"): value for key, value in options.items()}
    settings = make_settings({"rules": {"demeter-chain": data}})
    report = lint_text(text, settings)
    return [d for d in report.diagnostics if d.code == "FUR403"]


class ChainTest(unittest.TestCase):
    def test_depth_counts_the_attributes(self) -> None:
        self.assertEqual(chains_of("a.b.c.d.do()"), {("a", 4)})

    def test_a_subscript_is_crossed_without_counting(self) -> None:
        self.assertEqual(chains_of("a.b[0].c"), {("a", 2)})
        self.assertEqual(chains_of("a[0].b"), {("a", 1)})

    def test_a_call_ends_the_chain(self) -> None:
        self.assertEqual(chains_of("a.b().c.d"), {("a", 1), ("a.b()", 2)})

    def test_count_calls_crosses_the_call(self) -> None:
        self.assertEqual(chains_of("a.b().c.d", count_calls=True), {("a", 3)})

    def test_a_maximal_chain_is_read_once(self) -> None:
        chains = list(maximal_chains(ast.parse("a.b.c.d"), False))
        self.assertEqual(len(chains), 1)

    def test_what_the_chain_does_not_cross_has_its_own_chains(self) -> None:
        self.assertEqual(chains_of("a.b[c.d.e].f"), {("a", 2), ("c", 2)})
        self.assertEqual(
            chains_of("a.b(c.d, k=e.f).g", count_calls=True),
            {("a", 2), ("c", 1), ("e", 1)},
        )
        self.assertEqual(chains_of("a.b(c.d).g"), {("a", 1), ("a.b(c.d)", 1), ("c", 1)})

    def test_a_root_may_be_any_expression(self) -> None:
        self.assertEqual(chains_of("'x'.join.a"), {("'x'", 2)})
        self.assertEqual(chains_of("(a + b).c.d"), {("a + b", 2)})
        self.assertEqual(chains_of("f().a"), {("f()", 1)})

    def test_every_expression_counts(self) -> None:
        for text in (
            "a.b.c = 1",
            "del a.b.c",
            "x: a.b.c = 1",
            "@a.b.c\ndef f(): pass",
            "def f(x=a.b.c): pass",
            "def f(x: a.b.c): pass",
            "f'{a.b.c}'",
            "lambda: a.b.c",
            "[a.b.c for x in y]",
            "class C(a.b.c): pass",
        ):
            with self.subTest(text=text):
                self.assertIn(("a", 2), chains_of(text))


class ExemptionTest(unittest.TestCase):
    def test_a_root_of_ignore_roots_does_not_count_its_first_attribute(self) -> None:
        for root in ("self", "cls"):
            with self.subTest(root=root):
                text = f"{root}.repo.session.query()\n"
                self.assertEqual(chain_diagnostics(text, max_depth=2), [])
                self.assertEqual(len(chain_diagnostics(text, max_depth=1)), 1)

    def test_ignore_roots_is_configurable(self) -> None:
        text = "this.a.b.c.d\nself.a.b.c.d.e\n"
        found = chain_diagnostics(text, ignore_roots=["this"])
        self.assertEqual([d.span.start.line for d in found], [2])

    def test_imported_modules_are_ignored(self) -> None:
        for text in (
            "import os\nos.path.join.a.b.c\n",
            "import os as o\no.path.join.a.b.c\n",
            "import xml.dom\nxml.dom.minidom.a.b.c\n",
            "try:\n    import os\nexcept ImportError:\n    os = None\nos.a.b.c.d.e\n",
        ):
            with self.subTest(text=text):
                self.assertEqual(chain_diagnostics(text), [])

    def test_a_name_from_an_import_from_is_not_ignored(self) -> None:
        for text in (
            "from os import path\npath.a.b.c.d\n",
            "from os import path as p\np.a.b.c.d\n",
        ):
            with self.subTest(text=text):
                self.assertEqual(len(chain_diagnostics(text)), 1)

    def test_the_first_binding_decides(self) -> None:
        text = "from m import os\nimport os\nos.a.b.c.d\n"
        self.assertEqual(len(chain_diagnostics(text)), 1)
        text = "import os\nfrom m import os\nos.a.b.c.d\n"
        self.assertEqual(chain_diagnostics(text), [])

    def test_an_import_in_a_function_is_not_in_the_module_scope(self) -> None:
        text = "def f():\n    import os\n    return os.a.b.c.d\n"
        self.assertEqual(len(chain_diagnostics(text)), 1)

    def test_ignore_imported_modules_can_be_turned_off(self) -> None:
        text = "import os\nos.path.join.a.b\n"
        self.assertEqual(len(chain_diagnostics(text, ignore_imported_modules=False)), 1)

    def test_an_exempt_root_needs_a_name(self) -> None:
        text = "import os\nos.f().a.b.c.d\n"
        self.assertEqual(len(chain_diagnostics(text)), 1)
        text = "self().a.b.c.d\n"
        self.assertEqual(len(chain_diagnostics(text)), 1)


class DiagnosticTest(unittest.TestCase):
    def test_reference_a_b_c_d_do(self) -> None:
        diagnostic = chain_diagnostics("a.b.c.d.do()\n")[0]
        self.assertEqual(diagnostic.name, "demeter-chain")
        self.assertEqual(
            diagnostic.message, "Attribute chain `a.b.c.d.do` is too deep (4 > 3)"
        )
        self.assertEqual(
            diagnostic.help,
            "Long chains depend on the inner structure of other objects; consider asking the first object for what you need",
        )

    def test_reference_self_repo_session_query(self) -> None:
        diagnostic = chain_diagnostics("self.repo.session.query()\n", max_depth=1)[0]
        self.assertEqual(
            diagnostic.message,
            "Attribute chain `self.repo.session.query` is too deep (2 > 1)",
        )

    def test_a_b_call_c_d(self) -> None:
        self.assertEqual(chain_diagnostics("a.b().c.d\n", max_depth=2), [])
        found = chain_diagnostics("a.b().c.d\n", max_depth=1)
        self.assertEqual(len(found), 1)
        self.assertEqual(
            found[0].message, "Attribute chain `a.b().c.d` is too deep (2 > 1)"
        )
        self.assertEqual(len(chain_diagnostics("a.b().c.d\n", max_depth=0)), 2)

    def test_count_calls(self) -> None:
        text = "a.b().c.d.e\n"
        self.assertEqual(chain_diagnostics(text), [])
        found = chain_diagnostics(text, count_calls=True)
        self.assertEqual(len(found), 1)
        self.assertEqual(
            found[0].message, "Attribute chain `a.b().c.d.e` is too deep (4 > 3)"
        )

    def test_max_depth_is_strict(self) -> None:
        self.assertEqual(chain_diagnostics("a.b.c.d\n"), [])
        self.assertEqual(len(chain_diagnostics("a.b.c.d.e\n")), 1)

    def test_the_span_ends_on_the_last_attribute(self) -> None:
        for text in ("x = a.b.c.d.e()\n", "x = a.b.c.d.e[0]\n", "x = a.b.c.d.e\n"):
            with self.subTest(text=text):
                diagnostic = chain_diagnostics(text)[0]
                self.assertEqual(diagnostic.span.start.column, 5)
                self.assertEqual(diagnostic.span.end.column, 14)
                self.assertIn("`a.b.c.d.e`", diagnostic.message)

    def test_columns_are_in_characters(self) -> None:
        diagnostic = chain_diagnostics("é = é.b.c.d.e\n")[0]
        self.assertEqual(diagnostic.span.start.column, 5)
        self.assertEqual(diagnostic.span.end.column, 14)

    def test_a_chain_on_several_lines(self) -> None:
        diagnostic = chain_diagnostics("x = (\n    a.b\n    .c.d\n    .e\n)\n")[0]
        start, end = diagnostic.span.start, diagnostic.span.end
        self.assertEqual((start.line, start.column), (2, 5))
        self.assertEqual((end.line, end.column), (4, 7))
        self.assertIn("`a.b.c.d.e`", diagnostic.message)

    def test_foqa_covers_a_chain_on_several_lines(self) -> None:
        text = "x = (\n    a.b\n    .c.d\n    .e\n)  # foqa:FUR403\n"
        self.assertEqual(chain_diagnostics(text), [])

    def test_the_chain_is_cut_at_60_characters(self) -> None:
        name = "attribute_of_some_length"
        chain = f"root.{name}.{name}.{name}.{name}"
        diagnostic = chain_diagnostics(f"{chain}\n")[0]
        cited = chain[:59] + "…"
        self.assertEqual(
            diagnostic.message, f"Attribute chain `{cited}` is too deep (4 > 3)"
        )
        self.assertEqual(len(cited), 60)
        self.assertLessEqual(len(diagnostic.help), 160)

    def test_a_chain_too_deep_for_unparse_is_not_an_internal_error(self) -> None:
        text = "x = a" + ".b" * 3000 + "\n"
        diagnostic = chain_diagnostics(text)[0]
        self.assertEqual(
            diagnostic.message,
            "Attribute chain `a" + ".b" * 29 + "…` is too deep (3000 > 3)",
        )

    def test_a_string_on_several_lines_stays_on_one_line_of_help(self) -> None:
        text = 'x = f"""{y}\nz""".a.b.c.d\n'
        diagnostic = chain_diagnostics(text)[0]
        self.assertNotIn("\n", diagnostic.help)
        self.assertNotIn("\n", diagnostic.message)

    def test_several_chains_of_a_file(self) -> None:
        text = "a.b.c.d.e\nf(g.h.i.j.k.l)\n"
        found = chain_diagnostics(text)
        self.assertEqual(sorted(d.span.start.line for d in found), [1, 2])


if __name__ == "__main__":
    unittest.main()
