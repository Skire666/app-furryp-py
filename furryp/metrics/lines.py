"""Lines of code of a file and of a function (SPEC §10.1, §10.3, FUR101).

A line of code is a physical line covered by a significant token. Every token
of a docstring is left out, including the parentheses around it.
"""

import ast
import bisect
import tokenize
from collections.abc import Iterable
from dataclasses import dataclass

from furryp.core.ast_utils import (
    FUNCTION_TYPES,
    FunctionNode,
    docstring_of,
    first_line,
    last_line,
    node_end,
    node_start,
    tree_of,
)
from furryp.core.source import SourceFile

NOT_SIGNIFICANT_TOKENS = frozenset(
    {
        tokenize.COMMENT,
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENDMARKER,
        tokenize.ENCODING,
    }
)
DOCSTRING_OWNERS = (ast.Module, ast.ClassDef, *FUNCTION_TYPES)

type TextRange = tuple[tuple[int, int], tuple[int, int]]


@dataclass(frozen=True, slots=True)
class CodeLines:
    """The numbers of the lines of code of a file, sorted."""

    numbers: tuple[int, ...]

    @property
    def total(self) -> int:
        """The number of lines of code of the file."""
        return len(self.numbers)

    def between(self, first: int, last: int) -> int:
        """Return the number of lines of code from ``first`` to ``last``."""
        start = bisect.bisect_left(self.numbers, first)
        return bisect.bisect_right(self.numbers, last) - start


def _docstring_ranges(source: SourceFile) -> list[TextRange]:
    """Return the sorted text ranges of the docstrings of a file (§10.3)."""
    statements = [
        owner.body[0] for owner in ast.walk(tree_of(source)) if isinstance(owner, DOCSTRING_OWNERS) and owner.body
    ]
    return sorted(
        (node_start(source, statement), node_end(source, statement))
        for statement in statements
        if docstring_of(statement) is not None
    )


def _range_start(text_range: TextRange) -> tuple[int, int]:
    """Return the position where a text range starts."""
    return text_range[0]


def _in_ranges(ranges: list[TextRange], position: tuple[int, int]) -> bool:
    """Whether ``position`` lies in one of the sorted, disjoint ``ranges``."""
    index = bisect.bisect_right(ranges, position, key=_range_start) - 1
    return index >= 0 and position < ranges[index][1]


def significant_tokens(source: SourceFile) -> tuple[tokenize.TokenInfo, ...]:
    """Return the tokens of the file that make a line a line of code (§10.1)."""
    docstrings = _docstring_ranges(source)
    return tuple(
        token
        for token in source.tokens or ()
        if token.type not in NOT_SIGNIFICANT_TOKENS and not _in_ranges(docstrings, token.start)
    )


def code_lines_of(tokens: Iterable[tokenize.TokenInfo]) -> CodeLines:
    """Return the lines covered by ``tokens``, from their start to their end."""
    numbers = {line for token in tokens for line in range(token.start[0], token.end[0] + 1)}
    return CodeLines(tuple(sorted(numbers)))


def function_code_lines(function: FunctionNode, lines: CodeLines) -> int:
    """Return the lines of code from the first statement to the end of the body."""
    return lines.between(first_line(function.body[0]), last_line(function))
