"""What furryp must not do or read (SPEC §2.2, §3, §7.1, §9.4, §10.1)."""

import ast
import json
import os
import subprocess
import sys
import tomllib
import unittest

from tests.support import (
    CONFIG,
    PYPROJECT,
    REPO_ROOT,
    TempDirTestCase,
    run_furryp,
    run_main,
    write_files,
)

PACKAGE = REPO_ROOT / "furryp"
OUT_OF_SCOPE_OPTIONS = (
    "--output-format=json",
    "--unsafe-fixes",
    "--watch",
    "--no-cache",
    "--show-files",
    "--isolated",
    "-q",
    "--quiet",
    "-o=out.txt",
    "--output-file=out.txt",
    "--fix-only",
    "--exit-non-zero-on-fix",
    "--include=*.py",
    "--exclude=a.py",
    "--extend-exclude=a.py",
)
PARALLEL_MODULES = {"multiprocessing", "concurrent", "threading", "_thread", "asyncio"}
# The expected contract of SPEC §9.4, as written there.
LAYERS_CONTRACT = {
    "type": "layers",
    "name": "furryp-layers",
    "layers": [
        "furryp.cli",
        ["furryp.output", "furryp.report", "furryp.fix"],
        "furryp.lint",
        "furryp.config",
        "furryp.rules",
        "furryp.metrics",
        "furryp.core",
    ],
}


# C901 (12 > 10), I001, W291, W293 and blank lines: all left to ruff (checked
# with ruff 0.17.3), so furryp finds nothing in this file.
LEFT_TO_RUFF = (
    '"""Doc."""   \n\n\n\n'
    "import sys\nimport os   \n\n\n\n"
    "NAMES = (os.sep, sys.path)   \n   \n"
    "\n\ndef branches(x: int) -> int:\n"
    + "".join(f"    if x == {n}:\n        x += {n}\n" for n in range(11))
    + "    return x\n"
)


def _import_roots(node: ast.AST) -> list[str]:
    """Return the top-level modules named by an absolute import."""
    if isinstance(node, ast.Import):
        return [alias.name.split(".")[0] for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        return [node.module.split(".")[0]]
    return []


def _uses(node: ast.AST) -> list[str]:
    """Return the forbidden uses in one node of a module of ``furryp``."""
    found = []
    for root in _import_roots(node):
        if root == "__future__":
            found.append("from __future__")
        elif root in PARALLEL_MODULES:
            found.append(f"parallelism: {root}")
        elif root != "furryp" and root not in sys.stdlib_module_names:
            found.append(f"third-party import: {root}")
    if isinstance(node, ast.Attribute) and node.attr in {"stdin", "untokenize"}:
        found.append(node.attr)
    if isinstance(node, ast.Attribute) and node.attr == "splitlines":
        found.append("splitlines")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id == "input":
            found.append("input")
    return found


def forbidden_uses(text: str) -> list[str]:
    """Return what a module must not do (SPEC §2.2, §3, §7.1, §10.1)."""
    return [use for node in ast.walk(ast.parse(text)) for use in _uses(node)]


class CheckerTest(unittest.TestCase):
    """The scan of the package below can really fail."""

    def test_flagged_uses(self) -> None:
        for text, use in (
            ("import libcst\n", "third-party import: libcst"),
            ("from requests.api import get\n", "third-party import: requests"),
            ("from __future__ import annotations\n", "from __future__"),
            ("import multiprocessing\n", "parallelism: multiprocessing"),
            ("from concurrent.futures import Future\n", "parallelism: concurrent"),
            ("import threading\n", "parallelism: threading"),
            ("sys.stdin.read()\n", "stdin"),
            ("input()\n", "input"),
            ("tokenize.untokenize(tokens)\n", "untokenize"),
            ("text.splitlines()\n", "splitlines"),
        ):
            with self.subTest(text=text):
                self.assertEqual(forbidden_uses(text), [use])

    def test_clean_uses(self) -> None:
        for text in (
            "import ast\n",
            "from furryp.core.errors import UsageError\n",
            "from . import sibling\n",
            "x = 'a.splitlines()'\n",
        ):
            with self.subTest(text=text):
                self.assertEqual(forbidden_uses(text), [])


class PackageTest(unittest.TestCase):
    def test_package_has_no_forbidden_use(self) -> None:
        problems = [
            f"{path.relative_to(REPO_ROOT)}: {use}"
            for path in sorted(PACKAGE.rglob("*.py"))
            for use in forbidden_uses(path.read_text(encoding="utf-8"))
        ]
        self.assertEqual(problems, [])

    def test_unparse_only_displays_an_expression(self) -> None:
        # SPEC §7.1: ast.unparse may only show a chain in a message of FUR403.
        users = [
            path.relative_to(PACKAGE).as_posix()
            for path in sorted(PACKAGE.rglob("*.py"))
            if any(
                isinstance(node, ast.Attribute) and node.attr == "unparse"
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            )
        ]
        self.assertEqual(users, ["core/ast_utils.py"])


class ProjectFilesTest(unittest.TestCase):
    def test_python_version_and_no_optional_dependency(self) -> None:
        # The other dependencies: tests/test_version.py.
        with (REPO_ROOT / PYPROJECT).open("rb") as file:
            data = tomllib.load(file)
        self.assertEqual(data["project"]["requires-python"], ">=3.14")
        self.assertNotIn("optional-dependencies", data["project"])

    def test_layers_contract_of_the_repository(self) -> None:
        data = json.loads((REPO_ROOT / CONFIG).read_text(encoding="utf-8"))
        self.assertIn("tests", data["extend-exclude"])
        contracts = data["rules"]["layer-violation"]["contracts"]
        self.assertIn(LAYERS_CONTRACT, contracts)


class OutOfScopeTest(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        write_files(self.root, {PYPROJECT: "", "a.py": "x = 1\n"})

    def test_options_are_refused(self) -> None:
        for option in OUT_OF_SCOPE_OPTIONS:
            with self.subTest(option=option):
                code, out, err = run_main(["check", option, "a.py"], self.root)
                self.assertEqual((code, out), (2, ""))
                self.assertTrue(err.startswith("error: "), err)

    def test_commands_are_refused(self) -> None:
        for command in ("format", "server"):
            with self.subTest(command=command):
                code, out, err = run_main([command], self.root)
                self.assertEqual((code, out), (2, ""))
                self.assertTrue(err.startswith("error: "), err)

    def test_no_ansi_colours_even_when_forced(self) -> None:
        for arguments in (["check", "a.py"], ["check", "--help"], ["bogus"]):
            with self.subTest(arguments=arguments):
                result = run_furryp(arguments, self.root, {"FORCE_COLOR": "1"})
                self.assertNotIn("\x1b", result.stdout + result.stderr)

    def test_gitignore_is_not_read(self) -> None:
        write_files(self.root, {".gitignore": "a.py\n", "a.py": "x = a.b.c.d.e\n"})
        code, out, _ = run_main(["check", "--select", "FUR403"], self.root)
        self.assertEqual(code, 1)
        self.assertIn("a.py", out)

    def test_only_one_configuration_file_is_read(self) -> None:
        # A nested furryp.json is not read, or its invalid JSON would give 2.
        write_files(
            self.root,
            {
                CONFIG: '{"select": ["FUR102"]}',
                "sub/furryp.json": "{not json",
                "sub/b.py": "x = 1\n",
            },
        )
        for arguments, cwd in (
            (["check", "sub/b.py"], self.root),
            (["check", "b.py"], self.root / "sub"),
        ):
            with self.subTest(cwd=cwd):
                self.assertEqual(run_main(arguments, cwd)[0], 0)

    def test_standard_input_is_not_read(self) -> None:
        env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
        result = subprocess.run(
            [sys.executable, "-m", "furryp", "check", "-"],
            cwd=self.root,
            env=env,
            input="import os\n",
            capture_output=True,
            encoding="utf-8",
            check=False,
            timeout=60,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Failed to read file", result.stdout)
        self.assertIn("--> -:1:1", result.stdout)


class LeftToRuffTest(TempDirTestCase):
    def test_what_ruff_controls_is_not_flagged(self) -> None:
        write_files(self.root, {PYPROJECT: "", "a.py": LEFT_TO_RUFF})
        self.assertEqual(
            run_main(["check", "a.py"], self.root), (0, "All checks passed!\n", "")
        )


if __name__ == "__main__":
    unittest.main()
