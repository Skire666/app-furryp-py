"""Resolution of imported names (SPEC §10.5).

The table maps every name bound by an import of the module scope to its
target: ``import enum as e`` binds ``e`` to ``enum``, ``from enum import Enum
as E`` binds ``E`` to ``enum.Enum`` and ``import a.b`` binds ``a`` to ``a``.
The module scope is made of the top-level statements and of the blocks they
contain (``if``, ``try``, ``with``…), not of the bodies of functions and
classes.

A relative import keeps its dots (``from .m import x`` binds ``x`` to
``.m.x``) and ``*`` binds nothing. When a name is bound twice, the first
import wins: in ``try: from enum import StrEnum`` / ``except ImportError:
…``, the module tried first is the expected one. ``modules`` holds the names
whose first binding is an ``import x`` or ``import x as y`` (FUR403).
"""

import ast
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from furryp.core.ast_utils import DEFINITION_TYPES, DOT, IMPORT_TYPES, dotted_name

STAR = "*"
TYPE_CHECKING = "TYPE_CHECKING"
TYPING_TYPE_CHECKING = frozenset({"typing.TYPE_CHECKING", "typing_extensions.TYPE_CHECKING"})


def module_imports(tree: ast.Module | None) -> Iterator[ast.Import | ast.ImportFrom]:
    """Yield the imports of the module scope, in source order."""
    pending: list[ast.AST] = [] if tree is None else list(reversed(tree.body))
    while pending:
        node = pending.pop()
        if isinstance(node, IMPORT_TYPES):
            yield node
        elif not isinstance(node, DEFINITION_TYPES):
            pending.extend(reversed(list(ast.iter_child_nodes(node))))


def bindings(node: ast.Import | ast.ImportFrom) -> Iterator[tuple[str, str]]:
    """Yield the ``(name, target)`` pairs bound by an import."""
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.asname is None:
                root = alias.name.partition(DOT)[0]
                yield root, root
            else:
                yield alias.asname, alias.name
        return
    module = DOT * node.level + (node.module or "")
    prefix = module + DOT if node.module else module
    for alias in node.names:
        if alias.name != STAR:
            yield alias.asname or alias.name, prefix + alias.name


@dataclass(frozen=True, slots=True)
class ImportTable:
    """Names bound by the imports of a module, mapped to their targets."""

    targets: Mapping[str, str]
    modules: frozenset[str] = frozenset()

    def target(self, name: str) -> str | None:
        """Return the target of an imported name, or ``None``."""
        return self.targets.get(name)

    def resolve(self, node: ast.expr) -> str | None:
        """Return the dotted name of ``node``, its root replaced by its target.

        ``None`` if ``node`` is not a chain of names; a root that is not imported is kept as it is.
        """
        name = dotted_name(node)
        if name is None:
            return None
        root, dot, rest = name.partition(DOT)
        return self.targets.get(root, root) + dot + rest


def import_table(tree: ast.Module | None) -> ImportTable:
    """Return the table of the names imported in the module scope of ``tree``."""
    targets: dict[str, str] = {}
    modules: set[str] = set()
    for node in module_imports(tree):
        for name, target in bindings(node):
            if name not in targets and isinstance(node, ast.Import):
                modules.add(name)
            targets.setdefault(name, target)
    return ImportTable(targets, frozenset(modules))


def is_type_checking_test(test: ast.expr, imports: ImportTable) -> bool:
    """Whether ``test`` is ``TYPE_CHECKING`` as ruff sees it.

    That is the name, any ``x.TYPE_CHECKING`` attribute, or an alias of ``typing.TYPE_CHECKING``.
    """
    if isinstance(test, ast.Attribute):
        return test.attr == TYPE_CHECKING
    if isinstance(test, ast.Name):
        return test.id == TYPE_CHECKING or imports.resolve(test) in TYPING_TYPE_CHECKING
    return False
