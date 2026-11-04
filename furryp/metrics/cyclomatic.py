"""Cyclomatic complexity of a function, computed as C901 of ruff 0.17.3.

The score starts at 1. Each of these adds 1: ``if``, ``elif``, ``for``,
``while``, ``except``, the ``else`` of a ``try``, each ``case`` except a last
irrefutable one without guard, and a nested function, whose body counts too.
``else``, ``with``, ``finally``, boolean operators, ternaries, comprehensions
and ``lambda`` add nothing, as they are not branching statements for ruff.

One difference: a class defined in the function adds nothing, as it is measured
on its own (SPEC FUR401).

The walks use a stack: an ``elif`` chain can be deeper than the recursion limit.
"""

import ast

from furryp.core.ast_utils import BLOCK_NODES, FUNCTION_TYPES, FunctionNode

BRANCH_TYPES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    *FUNCTION_TYPES,
)
TRY_TYPES = (ast.Try, ast.TryStar)


def _is_irrefutable(pattern: ast.pattern) -> bool:
    """Whether a pattern always matches: ``_``, a name, or an ``|`` holding one."""
    stack = [pattern]
    while stack:
        current = stack.pop()
        if isinstance(current, ast.MatchOr):
            stack.extend(current.patterns)
        elif isinstance(current, ast.MatchAs):
            if current.pattern is None:
                return True
            stack.append(current.pattern)
    return False


def _match_branches(node: ast.Match) -> int:
    """Return the branches of a ``match``.

    A last irrefutable ``case`` without guard is like the ``else`` of an ``if``.
    """
    last = node.cases[-1]
    if last.guard is None and _is_irrefutable(last.pattern):
        return len(node.cases) - 1
    return len(node.cases)


def _branches(node: ast.AST) -> int:
    """Return what a statement adds to the score, without its children."""
    if isinstance(node, BRANCH_TYPES):
        return 1
    if isinstance(node, TRY_TYPES):
        return 1 if node.orelse else 0
    return _match_branches(node) if isinstance(node, ast.Match) else 0


def cyclomatic_complexity(function: FunctionNode) -> int:
    """Return the cyclomatic complexity of ``function``."""
    total = 1
    stack: list[ast.AST] = list(function.body)
    while stack:
        current = stack.pop()
        if not isinstance(current, ast.ClassDef):
            total += _branches(current)
            stack.extend(
                child
                for child in ast.iter_child_nodes(current)
                if isinstance(child, BLOCK_NODES)
            )
    return total
