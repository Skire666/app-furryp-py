"""Metrics of a file, computed once and on first use (SPEC §9.2).

``lint.runner`` creates one ``FileMetrics`` per file and shares it between the
rules; a run that selects no metric rule computes nothing.
"""

import ast
import bisect
import tokenize
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cached_property

from furryp.core.ast_utils import (
    BLOCK_NODES,
    DOT,
    FUNCTION_TYPES,
    FunctionNode,
    name_span,
    node_end,
    node_start,
    token_start,
    tree_of,
)
from furryp.core.diagnostic import Span
from furryp.core.source import SourceFile
from furryp.metrics.classes import ClassMetrics, class_metrics
from furryp.metrics.cognitive import ClauseKeywords, Contribution, clause_keywords, cognitive_contributions
from furryp.metrics.halstead import Halstead, counted_tokens, measure
from furryp.metrics.lines import CodeLines, code_lines_of, function_code_lines, significant_tokens


@dataclass(frozen=True, slots=True)
class FunctionMetrics:
    """Measures of a function; ``name`` is qualified, without ``<locals>``.

    A nested function counts in its parent for the cognitive complexity and is
    not evaluated alone: its ``contributions`` are empty.
    """

    name: str
    span: Span
    nested: bool
    code_lines: int
    halstead: Halstead
    contributions: tuple[Contribution, ...]

    @property
    def cognitive(self) -> int:
        """The cognitive complexity: the sum of the contributions."""
        return sum(contribution.points for contribution in self.contributions)


@dataclass(frozen=True, slots=True)
class _FunctionScope:
    """A function, with what its position in the file tells about it."""

    node: FunctionNode
    name: str
    nested: bool
    method: bool


def _function_scopes(tree: ast.Module) -> Iterator[_FunctionScope]:
    """Yield the functions of a module, in the order of the source.

    The walk uses a stack: an ``elif`` chain can be deeper than the recursion limit.
    """
    stack: list[tuple[ast.AST, str, bool, bool]] = [(tree, "", False, False)]
    while stack:
        node, prefix, nested, method = stack.pop()
        if isinstance(node, FUNCTION_TYPES):
            name = prefix + node.name
            yield _FunctionScope(node, name, nested, method)
            prefix, nested, method = name + DOT, True, False
        elif isinstance(node, ast.ClassDef):
            prefix, method = prefix + node.name + DOT, True
        children = [
            (child, prefix, nested, method) for child in ast.iter_child_nodes(node) if isinstance(child, BLOCK_NODES)
        ]
        stack.extend(reversed(children))


class FileMetrics:
    """The measures of a file; each of them is computed once, on first use."""

    def __init__(self, source: SourceFile) -> None:
        """Keep ``source``; nothing is measured yet."""
        self._source = source

    @cached_property
    def _significant(self) -> tuple[tokenize.TokenInfo, ...]:
        """The tokens that make a line a line of code."""
        return significant_tokens(self._source)

    @cached_property
    def _counted(self) -> tuple[tokenize.TokenInfo, ...]:
        """The tokens that Halstead counts."""
        return counted_tokens(self._significant)

    @cached_property
    def _code_lines(self) -> CodeLines:
        """The lines of code of the file."""
        return code_lines_of(self._significant)

    @cached_property
    def _clauses(self) -> ClauseKeywords:
        """The clause keywords of the file."""
        return clause_keywords(self._source)

    @cached_property
    def _scopes(self) -> tuple[_FunctionScope, ...]:
        """The functions of the file, in the order of the source."""
        return tuple(_function_scopes(tree_of(self._source)))

    @property
    def lines(self) -> int:
        """The number of physical lines of the file."""
        return len(self._source.lines)

    @property
    def code_lines(self) -> int:
        """The number of lines of code of the file."""
        return self._code_lines.total

    @cached_property
    def halstead(self) -> Halstead:
        """Halstead of every token of the file."""
        return measure(self._counted)

    @cached_property
    def functions(self) -> tuple[FunctionMetrics, ...]:
        """The measures of every function, in the order of the source."""
        return tuple(self._measure_function(scope) for scope in self._scopes)

    @cached_property
    def classes(self) -> tuple[ClassMetrics, ...]:
        """The measures of every class, in the order of the source."""
        return class_metrics(self._source)

    def _token_range(self, node: FunctionNode) -> tuple[int, int]:
        """Return the indexes of the counted tokens of a function, from the ``def`` or ``async`` keyword to its end.

        Decorators are left out.
        """
        start = node_start(self._source, node)
        end = node_end(self._source, node)
        return (
            bisect.bisect_left(self._counted, start, key=token_start),
            bisect.bisect_left(self._counted, end, key=token_start),
        )

    def _contributions(self, scope: _FunctionScope) -> tuple[Contribution, ...]:
        """Return the contributions of a function, none if it is nested."""
        if scope.nested:
            return ()
        return cognitive_contributions(scope.node, scope.method, self._source, self._clauses)

    def _measure_function(self, scope: _FunctionScope) -> FunctionMetrics:
        """Return the measures of a function."""
        node = scope.node
        first, last = self._token_range(node)
        return FunctionMetrics(
            name=scope.name,
            span=name_span(self._source, node),
            nested=scope.nested,
            code_lines=function_code_lines(node, self._code_lines),
            halstead=measure(self._counted[first:last]),
            contributions=self._contributions(scope),
        )
