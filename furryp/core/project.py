"""Modules of a project: names of files, imports and patterns (SPEC FUR402).

The name of a file is its path relative to the first source root that holds it,
in dotted notation: ``pkg/__init__.py`` is ``pkg``. Relative imports start from
the package of the module, and one that goes above the top level names nothing.

A pattern ``a.b`` matches ``a.b`` and the modules below it, but not ``a.bc``;
``*`` stands for exactly one segment.

As in ruff 0.17.3 (TID251), ``from X import y`` names the module ``X``, at the
position of the statement, and the member ``X.y``, at the position of ``y``. A
pattern that matches ``X`` is not tested again on its members, so that ``from
app.infra import x, y`` breaks a contract once.
"""

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePath

from furryp.core.ast_utils import BLOCK_NODES, DOT, IMPORT_TYPES
from furryp.core.names import STAR, ImportTable, is_type_checking_test

PACKAGE_MODULE = "__init__"
WILDCARD = "*"

type ImportNode = ast.Import | ast.ImportFrom


@dataclass(frozen=True, slots=True)
class ModuleName:
    """Dotted name of a file, and the package its relative imports start from."""

    name: str
    package: str


def module_name(relative: PurePath) -> ModuleName | None:
    """Return the module of a path relative to its source root; a root's own ``__init__.py`` has no name."""
    parts = relative.with_suffix("").parts
    if parts[-1:] == (PACKAGE_MODULE,):
        parts = parts[:-1]
        package = DOT.join(parts)
    else:
        package = DOT.join(parts[:-1])
    return ModuleName(DOT.join(parts), package) if parts else None


@dataclass(frozen=True, slots=True)
class ProjectContext:
    """The root of the project and its source roots, in the configured order."""

    root: Path
    source_roots: tuple[Path, ...] = ()

    def module_of(self, path: Path) -> ModuleName | None:
        """Return the module of the file at ``path``, ``None`` if it is outside of the source roots."""
        for source_root in self.source_roots:
            if path.is_relative_to(source_root):
                return module_name(path.relative_to(source_root))
        return None


def absolute_module(package: str, level: int, module: str | None) -> str | None:
    """Return the module named by ``from {dots}{module} import``, seen from ``package``.

    Return ``None`` if it goes above the top level.
    """
    if level == 0:
        return module
    segments = package.split(DOT) if package else []
    if level > len(segments):
        return None
    kept = segments[: len(segments) - level + 1]
    return DOT.join([*kept, module] if module else kept)


def module_matches(pattern: str, module: str) -> bool:
    """Whether ``module`` is ``pattern`` or below it (segment boundary)."""
    expected = pattern.split(DOT)
    segments = module.split(DOT)
    return len(segments) >= len(expected) and all(
        wanted in {WILDCARD, segment}
        for wanted, segment in zip(expected, segments, strict=False)
    )


def matched_prefix(pattern: str, module: str) -> str:
    """Return the part of ``module`` that ``pattern`` matches, without jokers."""
    return DOT.join(module.split(DOT)[: pattern.count(DOT) + 1])


@dataclass(frozen=True, slots=True)
class ImportTarget:
    """A module named by an import; ``parent`` is ``X`` for a member ``X.y``."""

    name: str
    node: ImportNode | ast.alias
    parent: str | None = None

    def matched_by(self, pattern: str) -> bool:
        """Whether ``pattern`` matches this target and not already its parent."""
        if not module_matches(pattern, self.name):
            return False
        return self.parent is None or not module_matches(pattern, self.parent)


def import_targets(node: ImportNode, package: str) -> Iterator[ImportTarget]:
    """Yield the modules named by an import, seen from ``package``."""
    if isinstance(node, ast.Import):
        for alias in node.names:
            yield ImportTarget(alias.name, alias)
        return
    module = absolute_module(package, node.level, node.module)
    if module is None:
        return
    yield ImportTarget(module, node)
    for alias in node.names:
        if alias.name != STAR:
            yield ImportTarget(module + DOT + alias.name, alias, module)


def _blocks(
    node: ast.AST, guarded: bool, imports: ImportTable
) -> list[tuple[ast.AST, bool]]:
    """Return the statements directly in ``node``, each with whether it runs only for a type checker.

    An ``else`` is executed code, as for ruff.
    """
    if isinstance(node, ast.If) and is_type_checking_test(node.test, imports):
        return [
            *((child, True) for child in node.body),
            *((child, guarded) for child in node.orelse),
        ]
    return [
        (child, guarded)
        for child in ast.iter_child_nodes(node)
        if isinstance(child, BLOCK_NODES)
    ]


def all_imports(
    tree: ast.Module, imports: ImportTable
) -> Iterator[tuple[ImportNode, bool]]:
    """Yield the imports of ``tree`` at any depth, in the order of the source.

    Each one comes with whether it is in the body of a ``TYPE_CHECKING`` block.

    The walk uses a stack: an ``elif`` chain can be deeper than the recursion
    limit.
    """
    stack: list[tuple[ast.AST, bool]] = [(tree, False)]
    while stack:
        node, guarded = stack.pop()
        if isinstance(node, IMPORT_TYPES):
            yield node, guarded
        else:
            stack.extend(reversed(_blocks(node, guarded, imports)))
