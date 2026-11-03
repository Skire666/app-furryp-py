"""Accessors on ``ast`` nodes shared by the rules (SPEC §10.2, §10.4).

``ast`` gives columns in UTF-8 bytes: every span built here converts them to
characters with ``positions.byte_to_char_column``. The accessors also keep
attribute chains short in the rules.
"""

import ast
import bisect
import tokenize

from furryp.core.diagnostic import Position, Span, line_span
from furryp.core.positions import byte_to_char_column
from furryp.core.source import SourceFile

FUNCTION_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)
DEFINITION_TYPES = (*FUNCTION_TYPES, ast.ClassDef)
IMPORT_TYPES = (ast.Import, ast.ImportFrom)
BLOCK_NODES = (ast.stmt, ast.excepthandler, ast.match_case)
DOT = "."

type FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
type Definition = FunctionNode | ast.ClassDef
type Located = ast.stmt | ast.expr | ast.alias


def first_line(node: ast.stmt) -> int:
    """Return the first line of a statement, decorators included."""
    decorators: list[ast.expr] = getattr(node, "decorator_list", [])
    return min((decorator.lineno for decorator in decorators), default=node.lineno)


def last_line(node: Located) -> int:
    """Return the last line of a node."""
    return node.end_lineno or node.lineno


def dotted_name(node: ast.expr | None) -> str | None:
    """Return ``a.b.c`` for a chain of ``Name`` and ``Attribute``, else ``None``."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return DOT.join(reversed(parts))


def docstring_of(node: ast.stmt) -> str | None:
    """Return the string of an ``Expr`` statement holding a ``str`` constant."""
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
        value = node.value.value
        return value if isinstance(value, str) else None
    return None


def statement_span(source: SourceFile, node: ast.stmt) -> Span:
    """Return the span of the first line of ``node``, from its first character.

    The span ends with the statement if it fits on its line, else at the end
    of its first line.
    """
    text = source.lines[node.lineno - 1]
    start = byte_to_char_column(text, node.col_offset) + 1
    if node.end_lineno == node.lineno and node.end_col_offset is not None:
        return line_span(
            node.lineno, start, byte_to_char_column(text, node.end_col_offset) + 1
        )
    return line_span(node.lineno, start, len(text) + 1)


def tree_of(source: SourceFile) -> ast.Module:
    """Return the AST of ``source``, empty if it does not parse."""
    return source.tree if source.tree is not None else ast.Module([], [])


def node_start(source: SourceFile, node: Located) -> tuple[int, int]:
    """Return the line and 0-indexed character column where ``node`` starts."""
    text = source.lines[node.lineno - 1]
    return node.lineno, byte_to_char_column(text, node.col_offset)


def node_end(source: SourceFile, node: Located) -> tuple[int, int]:
    """Return the line and 0-indexed character column where ``node`` ends."""
    line = last_line(node)
    return line, byte_to_char_column(source.lines[line - 1], node.end_col_offset or 0)


def node_span(source: SourceFile, node: Located) -> Span:
    """Return the span of a whole statement, expression or imported name, on any
    lines."""
    start_line, start_column = node_start(source, node)
    end_line, end_column = node_end(source, node)
    return Span(
        Position(start_line, start_column + 1), Position(end_line, end_column + 1)
    )


def expression_text(source: SourceFile, node: ast.expr) -> str:
    """Return ``ast.unparse(node)``, which writes a single line.

    A chain of a few hundred attributes is too deep for ``ast.unparse``: the
    rest of the line of the source is returned instead, from the start of ``node``.
    """
    try:
        return ast.unparse(node)
    except RecursionError:
        line, column = node_start(source, node)
        return source.lines[line - 1][column:]


def token_start(token: tokenize.TokenInfo) -> tuple[int, int]:
    """Return the line and column where ``token`` starts."""
    return token.start


def name_span(source: SourceFile, node: Definition) -> Span:
    """Return the span of the name that follows ``def`` or ``class`` (§10.2).

    Without tokens, the span of the first line of the definition is returned.
    """
    tokens = source.tokens or ()
    keyword = node_start(source, node)
    for token in tokens[bisect.bisect_left(tokens, keyword, key=token_start) :]:
        if token.type == tokenize.NAME and token.string == node.name:
            (line, column), (_, end) = token.start, token.end
            return line_span(line, column + 1, end + 1)
    return statement_span(source, node)
