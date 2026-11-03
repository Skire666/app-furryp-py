"""No implicit encoding in furryp/ (SPEC §3.1, §13).

Every ``open``, ``io.open``, ``os.fdopen``, ``Path.open``, ``read_text``,
``write_text`` and ``TextIOWrapper`` call needs an explicit ``encoding=``
(binary mode aside), and every text-mode write an explicit ``newline=``. A mode
that is not a literal, and every ``TextIOWrapper``, may write.
"""

import ast
import unittest

from tests.support import REPO_ROOT

PACKAGE = REPO_ROOT / "furryp"
OPEN_CALLS = {"open", "fdopen"}
TEXT_CALLS = OPEN_CALLS | {"read_text", "write_text", "TextIOWrapper"}
OPEN_MODULES = {"io", "builtins"}
WRITE_MODE_CHARACTERS = set("wax+")


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _mode_index(node: ast.Call, name: str) -> int:
    """Position of ``mode``: 1 for ``open(file, mode)``, ``io.open`` and
    ``os.fdopen``, 0 for the method ``Path.open(mode)``."""
    if name == "fdopen" or isinstance(node.func, ast.Name):
        return 1
    owner = node.func.value
    return 1 if isinstance(owner, ast.Name) and owner.id in OPEN_MODULES else 0


def _open_mode(node: ast.Call, name: str) -> str | None:
    """Mode of an ``open`` call; ``None`` when it is not a literal."""
    for keyword in node.keywords:
        if keyword.arg == "mode":
            expression = keyword.value
            break
    else:
        index = _mode_index(node, name)
        if len(node.args) <= index:
            return "r"
        expression = node.args[index]
    if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
        return expression.value
    return None


def _mode(node: ast.Call, name: str) -> str | None:
    if name in OPEN_CALLS:
        return _open_mode(node, name)
    if name == "TextIOWrapper":
        return None
    return "w" if name == "write_text" else "r"


def find_violations(source: str, filename: str = "<snippet>") -> list[str]:
    """Return one message per call that relies on an implicit setting."""
    problems = []
    for node in ast.walk(ast.parse(source, filename)):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name not in TEXT_CALLS:
            continue
        mode = _mode(node, name)
        if mode is not None and "b" in mode:
            continue
        keywords = {keyword.arg for keyword in node.keywords}
        location = f"{filename}:{node.lineno}"
        if "encoding" not in keywords:
            problems.append(f"{location}: {name}() without encoding=")
        writes = mode is None or bool(WRITE_MODE_CHARACTERS & set(mode))
        if writes and "newline" not in keywords:
            problems.append(f"{location}: {name}() writes text without newline=")
    return problems


class CheckerTest(unittest.TestCase):
    """The checker itself flags what it must flag."""

    def assertFlagged(self, source: str) -> None:
        self.assertTrue(find_violations(source), source)

    def assertClean(self, source: str) -> None:
        self.assertEqual(find_violations(source), [], source)

    def test_flagged_calls(self) -> None:
        for source in (
            'open("f")',
            'open("f", "r")',
            'open("f", "w", encoding="utf-8")',
            'open("f", mode)',
            "path.open()",
            'path.open("a", encoding="utf-8")',
            "path.read_text()",
            'files("furryp").joinpath("x").read_text()',
            'path.write_text("x")',
            'path.write_text("x", encoding="utf-8")',
            "io.TextIOWrapper(buffer)",
            'io.TextIOWrapper(buffer, encoding="utf-8")',
            'open("f", **options)',
            'io.open("f")',
            'io.open("f", "w", encoding="utf-8")',
            "os.fdopen(fd)",
            'os.fdopen(fd, "w", encoding="utf-8")',
        ):
            with self.subTest(source=source):
                self.assertFlagged(source)

    def test_clean_calls(self) -> None:
        for source in (
            'open("f", "rb")',
            'open("f", mode="wb")',
            'open("f", encoding="utf-8")',
            'open("f", "w", encoding="utf-8", newline="\\n")',
            'path.open("rb")',
            'path.read_text(encoding="utf-8")',
            'path.write_text("x", encoding="utf-8", newline="\\n")',
            "path.read_bytes()",
            'path.write_bytes(b"x")',
            'io.TextIOWrapper(buffer, encoding="utf-8", newline="\\n")',
            'io.open("f", "rb")',
            'io.open("f", "w", encoding="utf-8", newline="\\n")',
            'os.fdopen(fd, "wb")',
        ):
            with self.subTest(source=source):
                self.assertClean(source)


class PackageTest(unittest.TestCase):
    def test_package_has_no_implicit_encoding(self) -> None:
        sources = sorted(PACKAGE.rglob("*.py"))
        self.assertTrue(sources)
        problems = []
        for path in sources:
            source = path.read_bytes().decode("utf-8")
            problems += find_violations(source, str(path.relative_to(REPO_ROOT)))
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
