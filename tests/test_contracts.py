"""FUR402: modules of a project, contracts, their validation (SPEC §11).

The positions and the number of diagnostics are those of TID251 in ruff 0.17.3.
"""

import ast
import json
import unittest
from pathlib import Path, PurePosixPath
from typing import Any

from furryp.config.loader import ConfigError, load_configuration
from furryp.core.diagnostic import Diagnostic
from furryp.core.names import import_table
from furryp.core.project import (
    ProjectContext,
    absolute_module,
    all_imports,
    import_targets,
    matched_prefix,
    module_matches,
    module_name,
)
from furryp.output.settings import render_settings
from tests.support import (
    CONFIG,
    PYPROJECT,
    REPO_ROOT,
    TempDirTestCase,
    lint_text,
    make_settings,
    real_registry,
    run_main,
    write_files,
)

MODULE = "app/domain/m.py"
FORBIDDEN = {
    "type": "forbidden",
    "name": "pure",
    "source": ["app.domain"],
    "forbidden": ["app.infra"],
}
LAYERS = {
    "type": "layers",
    "name": "stack",
    "layers": ["app.api", ["app.service", "app.jobs"], "app.domain"],
}
INDEPENDENCE = {
    "type": "independence",
    "name": "apart",
    "modules": ["app.billing", "app.shipping"],
}


def contract_settings(*contracts: dict[str, Any], **options: object) -> Any:
    """Return settings with ``contracts`` and other FUR402 options."""
    data = {key.replace("_", "-"): value for key, value in options.items()}
    rule = {"contracts": list(contracts), **data}
    return make_settings({"rules": {"layer-violation": rule}})


def breaches(
    text: str, *contracts: dict[str, Any], name: str = MODULE, **options: object
) -> list:
    """Return the FUR402 diagnostics of ``text``, a file called ``name``."""
    report = lint_text(text, contract_settings(*contracts, **options), name)
    return [d for d in report.diagnostics if d.code == "FUR402"]


def positions(found: list) -> list[tuple[int, int]]:
    """Return the sorted positions of diagnostics."""
    return sorted((d.span.start.line, d.span.start.column) for d in found)


def whole_span(diagnostic: Diagnostic) -> tuple[int, int, int, int]:
    """Return where the span of a diagnostic starts and ends."""
    start, end = diagnostic.span.start, diagnostic.span.end
    return start.line, start.column, end.line, end.column


class ModuleNameTest(unittest.TestCase):
    def test_module_name(self) -> None:
        for path, name, package in (
            ("m.py", "m", ""),
            ("pkg/m.py", "pkg.m", "pkg"),
            ("pkg/sub/m.py", "pkg.sub.m", "pkg.sub"),
            ("pkg/__init__.py", "pkg", "pkg"),
            ("pkg/sub/__init__.py", "pkg.sub", "pkg.sub"),
        ):
            with self.subTest(path=path):
                module = module_name(PurePosixPath(path))
                assert module is not None
                self.assertEqual((module.name, module.package), (name, package))

    def test_the_init_of_a_source_root_has_no_name(self) -> None:
        self.assertIsNone(module_name(PurePosixPath("__init__.py")))

    def test_first_source_root_that_holds_the_file(self) -> None:
        root = Path("/project").resolve()
        project = ProjectContext(root, (root / "src", root))
        src = project.module_of(root / "src" / "app" / "m.py")
        other = project.module_of(root / "lib" / "m.py")
        assert src is not None and other is not None
        self.assertEqual(src.name, "app.m")
        self.assertEqual(other.name, "lib.m")

    def test_a_file_outside_of_the_source_roots(self) -> None:
        root = Path("/project").resolve()
        project = ProjectContext(root, (root / "src",))
        self.assertIsNone(project.module_of(root / "tests" / "m.py"))
        self.assertIsNone(project.module_of(root / "srcx" / "m.py"))


class RelativeImportTest(unittest.TestCase):
    def test_absolute_module(self) -> None:
        for package, level, module, expected in (
            ("app.domain", 0, "os", "os"),
            ("app.domain", 1, None, "app.domain"),
            ("app.domain", 1, "x", "app.domain.x"),
            ("app.domain", 2, None, "app"),
            ("app.domain", 2, "infra", "app.infra"),
            ("app.domain", 3, None, None),
            ("app.domain", 3, "x", None),
            ("", 1, None, None),
            ("", 1, "x", None),
        ):
            with self.subTest(package=package, level=level, module=module):
                self.assertEqual(absolute_module(package, level, module), expected)


class PatternTest(unittest.TestCase):
    def test_segment_boundary(self) -> None:
        self.assertTrue(module_matches("a.b", "a.b"))
        self.assertTrue(module_matches("a.b", "a.b.c"))
        self.assertTrue(module_matches("a.b", "a.b.c.d"))
        self.assertFalse(module_matches("a.b", "a.bc"))
        self.assertFalse(module_matches("a.b", "a"))
        self.assertFalse(module_matches("a.b", "x.a.b"))

    def test_joker_replaces_one_segment(self) -> None:
        self.assertTrue(module_matches("a.*", "a.b"))
        self.assertTrue(module_matches("a.*", "a.b.c"))
        self.assertFalse(module_matches("a.*", "a"))
        self.assertTrue(module_matches("a.*.c", "a.b.c"))
        self.assertTrue(module_matches("a.*.c", "a.b.c.d"))
        self.assertFalse(module_matches("a.*.c", "a.b.d"))
        self.assertFalse(module_matches("a.*.c", "a.b.x.c"))
        self.assertTrue(module_matches("*", "a"))

    def test_matched_prefix(self) -> None:
        self.assertEqual(matched_prefix("a.b", "a.b.c"), "a.b")
        self.assertEqual(matched_prefix("a.*", "a.b.c"), "a.b")
        self.assertEqual(matched_prefix("*.b", "a.b"), "a.b")


class ImportWalkTest(unittest.TestCase):
    def walked(self, text: str) -> list[tuple[str, bool]]:
        tree = ast.parse(text)
        return [
            (ast.unparse(node), guarded)
            for node, guarded in all_imports(tree, import_table(tree))
        ]

    def test_any_depth_in_source_order(self) -> None:
        text = (
            "import a\n"
            "def f():\n"
            "    import b\n"
            "class C:\n"
            "    import c\n"
            "try:\n"
            "    import d\n"
            "except E:\n"
            "    import e\n"
            "match x:\n"
            "    case 1:\n"
            "        import f\n"
            "import g\n"
        )
        self.assertEqual(
            [item[0] for item in self.walked(text)],
            [f"import {name}" for name in "abcdefg"],
        )

    def test_type_checking(self) -> None:
        text = (
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    import a\n"
            "    if x:\n"
            "        import b\n"
            "else:\n"
            "    import c\n"
            "if not TYPE_CHECKING:\n"
            "    import d\n"
            "def f():\n"
            "    if TYPE_CHECKING:\n"
            "        import e\n"
        )
        self.assertEqual(
            self.walked(text)[1:],
            [
                ("import a", True),
                ("import b", True),
                ("import c", False),
                ("import d", False),
                ("import e", True),
            ],
        )

    def test_targets(self) -> None:
        def names(text: str, package: str = "app.domain") -> list[str]:
            node = ast.parse(text).body[0]
            assert isinstance(node, (ast.Import, ast.ImportFrom))
            return [target.name for target in import_targets(node, package)]

        self.assertEqual(names("import a.b, c as d"), ["a.b", "c"])
        self.assertEqual(names("from a.b import c, d as e"), ["a.b", "a.b.c", "a.b.d"])
        self.assertEqual(names("from a import *"), ["a"])
        self.assertEqual(names("from ..infra import x"), ["app.infra", "app.infra.x"])
        self.assertEqual(names("from . import x"), ["app.domain", "app.domain.x"])
        self.assertEqual(names("from .... import x"), [])
        self.assertEqual(names("from .x import y", ""), [])


class ForbiddenTest(unittest.TestCase):
    def test_relative_import(self) -> None:
        found = breaches("from ..infra import x\n", FORBIDDEN)
        self.assertEqual(positions(found), [(1, 1)])
        self.assertEqual(found[0].name, "layer-violation")
        self.assertEqual(
            found[0].message,
            "Import of `app.infra` breaks contract `pure`: "
            "`app.domain` must not import `app.infra`",
        )
        self.assertEqual(
            found[0].help,
            "This dependency is forbidden; consider moving the shared code or inverting it",
        )

    def test_from_the_parent_package_points_at_the_name(self) -> None:
        for text in (
            "from .. import infra\n",
            "from app import infra\n",
            "from app import infra as other\n",
        ):
            with self.subTest(text=text):
                found = breaches(text, FORBIDDEN)
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0].span.start.column, text.index("infra") + 1)
                self.assertIn("Import of `app.infra` breaks", found[0].message)

    def test_import_points_at_the_name(self) -> None:
        found = breaches("import os, app.infra\nimport app.infra.db\n", FORBIDDEN)
        self.assertEqual(positions(found), [(1, 12), (2, 8)])
        self.assertEqual(
            [d.message.split(" breaks")[0] for d in found],
            ["Import of `app.infra`", "Import of `app.infra.db`"],
        )

    def test_a_statement_breaks_a_contract_once(self) -> None:
        for text in (
            "from app.infra import a, b, c\n",
            "from app.infra.db import a, b\n",
            "from ..infra import a, b\n",
            "from app.infra import *\n",
        ):
            with self.subTest(text=text):
                self.assertEqual(positions(breaches(text, FORBIDDEN)), [(1, 1)])

    def test_only_the_forbidden_names_of_a_statement(self) -> None:
        found = breaches("from app import other, infra, third\n", FORBIDDEN)
        self.assertEqual(positions(found), [(1, 24)])

    def test_segment_boundaries(self) -> None:
        for text in (
            "import app.infrax\n",
            "from app.infrax import q\n",
            "from app import infrax\n",
            "import app\n",
            "from app import domain\n",
        ):
            with self.subTest(text=text):
                self.assertEqual(breaches(text, FORBIDDEN), [])
        text = "from app.infra import x\n"
        self.assertEqual(breaches(text, FORBIDDEN, name="app/domainx/m.py"), [])

    def test_a_relative_import_above_the_top_level_is_ignored(self) -> None:
        self.assertEqual(breaches("from ...... import infra\n", FORBIDDEN), [])

    def test_any_depth(self) -> None:
        text = "def f():\n    from app.infra import x\n"
        self.assertEqual(positions(breaches(text, FORBIDDEN)), [(2, 5)])

    def test_first_pattern_in_order_like_tid251(self) -> None:
        contract = {**FORBIDDEN, "forbidden": ["app", "app.infra"]}
        found = breaches("from app.infra import x\n", contract)
        self.assertEqual(len(found), 1)
        self.assertIn("must not import `app`", found[0].message)
        found = breaches("from app import infra\n", contract)
        self.assertEqual(positions(found), [(1, 1), (1, 17)])
        self.assertIn("must not import `app`", found[0].message)
        self.assertIn("must not import `app.infra`", found[1].message)

    def test_a_folded_import_points_at_the_line_of_the_name(self) -> None:
        text = "from app import (\n    other,\n    infra,\n)\n"
        self.assertEqual(positions(breaches(text, FORBIDDEN)), [(3, 5)])

    def test_foqa_at_the_end_of_a_folded_import(self) -> None:
        text = "from app import (\n    other,\n    infra,\n)  # foqa:FUR402\n"
        self.assertEqual(breaches(text, FORBIDDEN), [])

    def test_a_folded_statement_is_spanned_whole(self) -> None:
        text = "from app.infra import (\n    a,\n    b,\n)\n"
        self.assertEqual(whole_span(breaches(text, FORBIDDEN)[0]), (1, 1, 4, 2))

    def test_an_imported_name_is_spanned_whole(self) -> None:
        for text, expected in (
            ("from app import infra\n", (1, 17, 1, 22)),
            ("from app import infra as other\n", (1, 17, 1, 31)),
            ("import app.infra\n", (1, 8, 1, 17)),
            ("import app.infra as other\n", (1, 8, 1, 26)),
            ("from app import (\n    infra as other,\n)\n", (2, 5, 2, 19)),
        ):
            with self.subTest(text=text):
                found = breaches(text, FORBIDDEN)
                self.assertEqual([whole_span(item) for item in found], [expected])

    def test_a_joker_cites_the_concrete_modules(self) -> None:
        contract = {
            "type": "forbidden",
            "name": "pure",
            "source": ["app.*.domain"],
            "forbidden": ["app.*.infra"],
        }
        found = breaches(
            "from app.y.infra.db import x\n", contract, name="app/x/domain/m.py"
        )
        self.assertEqual(
            found[0].message,
            "Import of `app.y.infra.db` breaks contract `pure`: "
            "`app.x.domain` must not import `app.y.infra`",
        )


class LayersTest(unittest.TestCase):
    def test_a_module_never_imports_a_higher_layer(self) -> None:
        found = breaches("from app.api import routes\n", LAYERS)
        self.assertEqual(positions(found), [(1, 1)])
        self.assertEqual(
            found[0].message,
            "Import of `app.api` breaks contract `stack`: "
            "`app.domain` must not import `app.api`",
        )

    def test_help(self) -> None:
        found = breaches("import app.api\n", LAYERS)
        self.assertEqual(
            found[0].help,
            "A layer only imports the layers below it; consider inverting this dependency",
        )

    def test_a_lower_layer_can_be_imported(self) -> None:
        text = "import app.domain\nfrom app.service import x\n"
        self.assertEqual(breaches(text, LAYERS, name="app/api/m.py"), [])

    def test_the_same_layer_can_be_imported(self) -> None:
        self.assertEqual(breaches("import app.domain.x\n", LAYERS), [])

    def test_a_sublist_is_one_level(self) -> None:
        text = "import app.jobs\n"
        self.assertEqual(breaches(text, LAYERS, name="app/service/m.py"), [])
        text = "import app.service\n"
        self.assertEqual(breaches(text, LAYERS, name="app/jobs/m.py"), [])

    def test_a_sublist_is_above_the_lower_layers(self) -> None:
        for name in ("app.service", "app.jobs"):
            with self.subTest(name=name):
                self.assertEqual(len(breaches(f"import {name}\n", LAYERS)), 1)

    def test_modules_outside_of_the_layers_are_free(self) -> None:
        self.assertEqual(
            breaches("import app.api\n", LAYERS, name="app/other/m.py"), []
        )
        self.assertEqual(breaches("import os\nimport app.other\n", LAYERS), [])

    def test_from_app_import_name(self) -> None:
        found = breaches("from app import api, service, other\n", LAYERS)
        self.assertEqual(positions(found), [(1, 17), (1, 22)])

    def test_the_most_specific_pattern_decides_the_level(self) -> None:
        contract = {"type": "layers", "name": "stack", "layers": ["app", "app.core"]}
        text = "import app.other\n"
        self.assertEqual(len(breaches(text, contract, name="app/core/m.py")), 1)
        self.assertEqual(breaches("import app.core\n", contract, name="app/m.py"), [])
        self.assertEqual(
            breaches("import app.core.x\n", contract, name="app/core/m.py"), []
        )
        contract = {"type": "layers", "name": "stack", "layers": ["app.api", "app"]}
        self.assertEqual(
            breaches("import app.other\n", contract, name="app/api/m.py"), []
        )
        found = breaches("from app import api\n", contract, name="app/m.py")
        self.assertEqual(positions(found), [(1, 17)])

    def test_several_contracts_give_several_diagnostics(self) -> None:
        other = {
            "type": "forbidden",
            "name": "other",
            "source": ["app.domain"],
            "forbidden": ["app.api"],
        }
        found = breaches("import app.api\n", LAYERS, other)
        self.assertEqual(len(found), 2)
        self.assertIn("`stack`", found[0].message)
        self.assertIn("`other`", found[1].message)


class SpecificityTest(unittest.TestCase):
    """The level of a module is that of its most specific pattern."""

    def test_more_segments_win_in_either_order(self) -> None:
        for layers in (["app", "app.model"], ["app.model", "app"]):
            with self.subTest(layers=layers):
                contract = {"type": "layers", "name": "stack", "layers": layers}
                low, high = ("app/model/m.py", "app/m.py")
                if layers[0] == "app.model":
                    low, high = high, low
                found = breaches(
                    "import app.model\nimport app.other\n", contract, name=low
                )
                self.assertEqual(len(found), 1)
                text = "import app.model.x\nimport app.other\n"
                self.assertEqual(breaches(text, contract, name=high), [])

    def test_a_literal_wins_over_a_joker(self) -> None:
        contract = {"type": "layers", "name": "stack", "layers": ["app.*", "app.model"]}
        found = breaches("import app.view\n", contract, name="app/model/m.py")
        self.assertEqual(len(found), 1)
        self.assertIn("`app.model` must not import `app.view`", found[0].message)
        self.assertEqual(
            breaches("import app.model\n", contract, name="app/view/m.py"), []
        )

    def test_a_tie_gives_the_highest_layer(self) -> None:
        contract = {"type": "layers", "name": "stack", "layers": ["app.*", "*.model"]}
        self.assertEqual(
            breaches("import app.view\n", contract, name="app/model/m.py"), []
        )


class MvpTest(TempDirTestCase):
    """The obvious cases of an MVP: the view does not reach the model, and the
    model knows nobody. Two ``forbidden`` contracts say it, on real files."""

    CONFIG = {
        "rules": {
            "layer-violation": {
                "contracts": [
                    {
                        "type": "forbidden",
                        "name": "view-without-model",
                        "source": ["app.view"],
                        "forbidden": ["app.model"],
                    },
                    {
                        "type": "forbidden",
                        "name": "model-alone",
                        "source": ["app.model"],
                        "forbidden": ["app.view", "app.presenter"],
                    },
                ]
            }
        }
    }
    INIT = {
        "app/__init__.py": "",
        "app/model/__init__.py": "",
        "app/view/__init__.py": "",
        "app/presenter/__init__.py": "",
    }

    def setUp(self) -> None:
        super().setUp()
        write_files(
            self.root, {PYPROJECT: "", CONFIG: json.dumps(self.CONFIG), **self.INIT}
        )

    def check(self, relative: str, text: str) -> tuple[int, str]:
        write_files(self.root, {relative: text})
        code, stdout, _ = run_main(["check", "--select", "FUR402", relative], self.root)
        return code, stdout

    def test_every_way_for_a_view_to_import_the_model(self) -> None:
        for text in (
            "from app.model import User\n",
            "from app.model.user import User\n",
            "import app.model\n",
            "import app.model.user\n",
            "import app.model.user as user\n",
            "from app import model\n",
            "from app import model as data\n",
            "from ..model import User\n",
            "from ..model.user import User\n",
            "from .. import model\n",
            "from app.model import *\n",
            "def show():\n    from app.model import User\n",
            "class Screen:\n    from app.model import User\n",
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n    from app.model import User\n",
            "try:\n    from app.model import User\nexcept ImportError:\n    User = None\n",
        ):
            with self.subTest(text=text):
                code, stdout = self.check("app/view/screen.py", text)
                self.assertEqual(code, 1, stdout)
                self.assertIn("breaks contract `view-without-model`", stdout)
                self.assertIn("`app.view` must not import `app.model`", stdout)

    def test_the_package_of_the_view_counts_too(self) -> None:
        code, stdout = self.check("app/view/__init__.py", "from ..model import User\n")
        self.assertEqual(code, 1, stdout)

    def test_a_single_file_per_role(self) -> None:
        code, stdout = self.check("app/view.py", "from app.model import User\n")
        self.assertEqual(code, 1, stdout)
        code, stdout = self.check("app/view.py", "from .model import User\n")
        self.assertEqual(code, 1, stdout)

    def test_the_model_knows_nobody(self) -> None:
        for text, forbidden in (
            ("from app.view import Screen\n", "app.view"),
            ("from app.presenter import Main\n", "app.presenter"),
            ("from .. import view\n", "app.view"),
        ):
            with self.subTest(text=text):
                code, stdout = self.check("app/model/user.py", text)
                self.assertEqual(code, 1, stdout)
                self.assertIn(f"`app.model` must not import `{forbidden}`", stdout)

    def test_what_an_mvp_allows(self) -> None:
        for relative, text in (
            (
                "app/presenter/main.py",
                "from app.model import User\nfrom app.view import S\n",
            ),
            (
                "app/presenter/main.py",
                "from ..model import User\nfrom ..view import S\n",
            ),
            ("app/view/screen.py", "from app.presenter import Main\n"),
            ("app/view/screen.py", "from app.view.widgets import Button\n"),
            ("app/view/screen.py", "from . import widgets\n"),
            ("app/view/screen.py", "from app.modeling import helper\n"),
            ("app/model/user.py", "from app.model.base import Base\n"),
            ("app/modelview/screen.py", "from app.model import User\n"),
            ("app/view/screen.py", "import os\nfrom app import presenter, utils\n"),
        ):
            with self.subTest(relative=relative, text=text):
                code, stdout = self.check(relative, text)
                self.assertEqual((code, stdout), (0, "All checks passed!\n"))

    def test_a_feature_layout_with_a_joker(self) -> None:
        contract = {
            "type": "forbidden",
            "name": "view-without-model",
            "source": ["app.*.view"],
            "forbidden": ["app.*.model"],
        }
        found = breaches(
            "from app.user.model import User\n", contract, name="app/user/view.py"
        )
        self.assertEqual(len(found), 1)
        self.assertIn(
            "`app.user.view` must not import `app.user.model`", found[0].message
        )
        found = breaches(
            "from app.order.model import Order\n", contract, name="app/user/view.py"
        )
        self.assertEqual(len(found), 1)
        self.assertEqual(
            breaches(
                "from app.user.presenter import P\n", contract, name="app/user/view.py"
            ),
            [],
        )

    def test_an_indirect_dependency_is_the_choice_of_the_developer(self) -> None:
        for text in (
            "from app.presenter import User\n",
            "from app import User\n",
            "import app\n",
            "import importlib\nimportlib.import_module('app.model')\n",
        ):
            with self.subTest(text=text):
                code, _ = self.check("app/view/screen.py", text)
                self.assertEqual(code, 0)

    def test_layers_are_not_strict_so_they_do_not_say_it_alone(self) -> None:
        layers = {
            "type": "layers",
            "name": "stack",
            "layers": ["app.view", "app.presenter", "app.model"],
        }
        text = "from app.model import User\n"
        self.assertEqual(breaches(text, layers, name="app/view/m.py"), [])
        found = breaches("from app.view import Screen\n", layers, name="app/model/m.py")
        self.assertEqual(len(found), 1)


class IndependenceTest(unittest.TestCase):
    def test_modules_do_not_import_each_other(self) -> None:
        found = breaches(
            "import app.shipping.rates\n", INDEPENDENCE, name="app/billing/m.py"
        )
        self.assertEqual(
            found[0].message,
            "Import of `app.shipping.rates` breaks contract `apart`: "
            "`app.billing` must not import `app.shipping`",
        )
        self.assertEqual(
            found[0].help,
            "These modules must stay independent; consider moving the shared code to a common module",
        )
        found = breaches("import app.billing\n", INDEPENDENCE, name="app/shipping/m.py")
        self.assertEqual(len(found), 1)

    def test_a_module_can_import_itself_and_others(self) -> None:
        text = "import app.billing.x\nimport app.other\nfrom . import y\n"
        self.assertEqual(breaches(text, INDEPENDENCE, name="app/billing/m.py"), [])
        self.assertEqual(
            breaches("import app.billing\n", INDEPENDENCE, name="app/m.py"), []
        )

    def test_with_a_joker_each_module_counts_apart(self) -> None:
        contract = {"type": "independence", "name": "apart", "modules": ["app.*"]}
        found = breaches(
            "from app.shipping import x\n", contract, name="app/billing/m.py"
        )
        self.assertEqual(len(found), 1)
        self.assertIn("`app.billing` must not import `app.shipping`", found[0].message)
        self.assertEqual(
            breaches("from app.billing import x\n", contract, name="app/billing/m.py"),
            [],
        )
        found = breaches(
            "from app import billing, shipping\n", contract, name="app/billing/m.py"
        )
        self.assertEqual(positions(found), [(1, 26)])


class TypeCheckingTest(unittest.TestCase):
    TEXT = (
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from app.infra import x\n"
        "else:\n"
        "    from app.infra import y\n"
    )

    def test_included_by_default_like_tid251(self) -> None:
        self.assertEqual(positions(breaches(self.TEXT, FORBIDDEN)), [(3, 5), (5, 5)])

    def test_can_be_left_out_but_not_its_else(self) -> None:
        found = breaches(self.TEXT, FORBIDDEN, include_type_checking=False)
        self.assertEqual(positions(found), [(5, 5)])

    def test_every_form_of_the_test(self) -> None:
        for prelude, test in (
            ("import typing\n", "typing.TYPE_CHECKING"),
            ("import typing as t\n", "t.TYPE_CHECKING"),
            ("from typing import TYPE_CHECKING as TC\n", "TC"),
        ):
            with self.subTest(test=test):
                text = f"{prelude}if {test}:\n    from app.infra import x\n"
                found = breaches(text, FORBIDDEN, include_type_checking=False)
                self.assertEqual(found, [])


class SourceRootsTest(unittest.TestCase):
    def test_module_relative_to_the_source_root(self) -> None:
        text = "from app.infra import x\n"
        found = breaches(
            text, FORBIDDEN, name="src/app/domain/m.py", source_roots=["src"]
        )
        self.assertEqual(len(found), 1)
        found = breaches(text, FORBIDDEN, name="src/app/domain/m.py")
        self.assertEqual(found, [])

    def test_a_file_outside_of_the_source_roots_is_not_checked(self) -> None:
        text = "from app.infra import x\n"
        self.assertEqual(breaches(text, FORBIDDEN, source_roots=["src"]), [])

    def test_a_package_init(self) -> None:
        name = "app/domain/__init__.py"
        self.assertEqual(
            len(breaches("from ..infra import x\n", FORBIDDEN, name=name)), 1
        )
        self.assertEqual(breaches("from .infra import x\n", FORBIDDEN, name=name), [])

    def test_without_contract_nothing_is_read(self) -> None:
        self.assertEqual(breaches("from app.infra import x\n"), [])

    def test_a_contract_applies_to_a_real_tree(self) -> None:
        settings = contract_settings(FORBIDDEN)
        report = lint_text("from ..infra import x\n", settings, MODULE)
        self.assertEqual(report.diagnostics[0].path, REPO_ROOT / MODULE)


class ContractValidationTest(TempDirTestCase):
    def error(self, contract: object) -> str:
        data = {"rules": {"layer-violation": {"contracts": [contract]}}}
        write_files(self.root, {CONFIG: json.dumps(data)})
        with self.assertRaises(ConfigError) as caught:
            load_configuration(self.root, Path(CONFIG), real_registry())
        return str(caught.exception).removeprefix(f"{CONFIG}: ")

    PATH = "rules.layer-violation.contracts[0]"

    def test_a_contract_must_be_an_object(self) -> None:
        self.assertEqual(
            self.error("x"), f"{self.PATH}: expected an object, got string"
        )

    def test_missing_type(self) -> None:
        self.assertEqual(self.error({"name": "x"}), f'{self.PATH}: missing key "type"')

    def test_unknown_type(self) -> None:
        for value, shown in (
            ("other", '"other"'),
            (["layers"], '["layers"]'),
            (1, "1"),
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    self.error({"type": value, "name": "x"}),
                    f"{self.PATH}.type: must be one of "
                    f'"forbidden", "layers", "independence", got {shown}',
                )

    def test_missing_keys(self) -> None:
        for contract, key in (
            ({"type": "forbidden", "source": [], "forbidden": []}, "name"),
            ({"type": "forbidden", "name": "x", "forbidden": []}, "source"),
            ({"type": "forbidden", "name": "x", "source": []}, "forbidden"),
            ({"type": "layers", "name": "x"}, "layers"),
            ({"type": "independence", "name": "x"}, "modules"),
        ):
            with self.subTest(key=key):
                self.assertEqual(
                    self.error(contract), f'{self.PATH}: missing key "{key}"'
                )

    def test_a_key_of_another_type_is_unknown(self) -> None:
        contract = {"type": "layers", "name": "x", "layers": [], "source": []}
        self.assertEqual(self.error(contract), f"{self.PATH}.source: unknown key")

    def test_a_close_key_is_suggested(self) -> None:
        contract = {"type": "layers", "name": "x", "layer": []}
        self.assertEqual(
            self.error(contract),
            f'{self.PATH}.layer: unknown key (did you mean "layers"?)',
        )

    def test_wrong_types(self) -> None:
        for contract, path, problem in (
            (
                {"type": "layers", "name": 1, "layers": []},
                "name",
                "expected a string, got integer",
            ),
            (
                {"type": "layers", "name": "x", "layers": "a"},
                "layers",
                "expected an array, got string",
            ),
            (
                {"type": "layers", "name": "x", "layers": [1]},
                "layers[0]",
                "expected an array, got integer",
            ),
            (
                {"type": "layers", "name": "x", "layers": [["a", 1]]},
                "layers[0][1]",
                "expected a string, got integer",
            ),
            (
                {"type": "independence", "name": "x", "modules": [1]},
                "modules[0]",
                "expected a string, got integer",
            ),
        ):
            with self.subTest(path=path):
                self.assertEqual(self.error(contract), f"{self.PATH}.{path}: {problem}")

    def test_a_pattern_is_not_validated_like_ruff_banned_api(self) -> None:
        contract = {**FORBIDDEN, "forbidden": ["a..b", ""]}
        self.assertEqual(breaches("from a.b import c\n", contract), [])

    def test_options_of_the_rule(self) -> None:
        settings = make_settings({"rules": {"layer-violation": {}}})
        options = settings.rules["layer-violation"]
        self.assertEqual(options.source_roots, (".",))
        self.assertTrue(options.include_type_checking)
        self.assertEqual(options.contracts, ())

    def test_settings_round_trip(self) -> None:
        data = {
            "rules": {
                "layer-violation": {
                    "source-roots": ["src"],
                    "contracts": [FORBIDDEN, LAYERS, INDEPENDENCE],
                }
            }
        }
        write_files(self.root, {CONFIG: json.dumps(data)})
        registry = real_registry()
        configuration = load_configuration(self.root, Path(CONFIG), registry)
        _, _, text = render_settings(configuration).partition("\n{")
        dumped = json.loads("{" + text)
        rule = dumped["rules"]["layer-violation"]
        self.assertEqual(rule["contracts"], [FORBIDDEN, LAYERS, INDEPENDENCE])
        write_files(self.root, {"saved.json": json.dumps(dumped)})
        reloaded = load_configuration(self.root, Path("saved.json"), registry)
        self.assertEqual(reloaded.settings, configuration.settings)


if __name__ == "__main__":
    unittest.main()
