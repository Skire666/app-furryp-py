"""Source files, read once and shared by every rule (SPEC §3.1, §9.2, §10.1).

A source is read as bytes; its encoding comes from ``tokenize.detect_encoding``
(UTF-8 by default, BOM and coding declaration respected, never the locale) and
the bytes are decoded with ``bytes.decode``, so line breaks are kept as they
are. Tokens, logical lines and AST are computed once, at loading time.
"""

import ast
import bisect
import io
import tokenize
import warnings
from dataclasses import dataclass
from pathlib import Path

from furryp.core.diagnostic import Position, Span
from furryp.core.positions import TextIndex, first_line_break, split_lines, text_index

DEFAULT_NEWLINE = "\n"
NOT_STATEMENT_TOKENS = frozenset(
    {tokenize.COMMENT, tokenize.NL, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING, tokenize.ENDMARKER}
)


class SourceReadError(Exception):
    """The file cannot be read (missing path, insufficient permissions)."""


class SourceDecodeError(Exception):
    """The bytes of the file are not valid in its detected encoding."""


@dataclass(frozen=True, slots=True)
class SyntaxProblem:
    """First tokenize or parse error of a file, with its position."""

    message: str
    span: Span


def _first_line(lines: tuple[int, int]) -> int:
    """Return the first line of a line range."""
    return lines[0]


@dataclass(frozen=True, slots=True)
class LogicalLines:
    """Physical line ranges of the logical lines (tokens up to ``NEWLINE``)."""

    ranges: tuple[tuple[int, int], ...]

    def range_of(self, line: int) -> tuple[int, int]:
        """Return the first and last lines of the logical line of ``line``.

        A line outside any logical line (comment or blank line between two statements) is its own range.
        """
        position = bisect.bisect_right(self.ranges, line, key=_first_line) - 1
        if position >= 0 and self.ranges[position][1] >= line:
            return self.ranges[position]
        return (line, line)


@dataclass(frozen=True, slots=True)
class SourceFile:
    """A decoded source file; ``syntax_error`` is set if it does not parse.

    ``tokens`` is ``None`` when tokenizing fails and ``tree`` when parsing
    fails; ``syntax_error`` is then the first of the two errors.
    """

    path: Path
    display: str
    text: str
    encoding: str
    newline: str
    lines: tuple[str, ...]
    index: TextIndex
    tokens: tuple[tokenize.TokenInfo, ...] | None
    logical: LogicalLines
    tree: ast.Module | None
    syntax_error: SyntaxProblem | None

    def line_bounds(self, line: int) -> tuple[int, int]:
        """Return the text indexes of the start of ``line`` and of the next line.

        The second index is the length of the text for the last line.
        """
        starts = self.index.starts
        following = starts[line] if line < len(starts) else len(self.text)
        return starts[line - 1], following


def read_source(path: Path, display: str) -> SourceFile:
    """Read, decode and analyse the file at ``path``."""
    try:
        data = path.read_bytes()
    except OSError as error:
        raise SourceReadError(error.strerror or str(error)) from None
    return decode_source(path, display, data)


def decode_source(path: Path, display: str, data: bytes) -> SourceFile:
    """Decode ``data`` in its detected encoding, then analyse it."""
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
        text = data.decode(encoding)
    except (SyntaxError, UnicodeDecodeError, LookupError) as error:
        raise SourceDecodeError(str(error)) from None
    return parse_source(path, display, text, encoding)


def parse_source(path: Path, display: str, text: str, encoding: str) -> SourceFile:
    """Analyse a decoded text: lines, tokens, logical lines and AST."""
    lines = split_lines(text)
    tree, parse_error = _parse(text, lines)
    tokens, token_error = _tokenize(text, lines)
    return SourceFile(
        path=path,
        display=display,
        text=text,
        encoding=encoding,
        newline=first_line_break(text) or DEFAULT_NEWLINE,
        lines=lines,
        index=text_index(text),
        tokens=tokens,
        logical=LogicalLines(_logical_ranges(tokens or ())),
        tree=tree,
        syntax_error=parse_error or token_error,
    )


def _parse(text: str, lines: tuple[str, ...]) -> tuple[ast.Module | None, SyntaxProblem | None]:
    """Parse ``text`` without emitting ``SyntaxWarning``."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return ast.parse(text), None
    except SyntaxError as error:
        start = _clamp(lines, error.lineno or 1, error.offset or 1)
        end = _clamp(lines, error.end_lineno or 0, error.end_offset or 0)
        return None, SyntaxProblem(error.msg, Span(start, max(start, end)))


def _tokenize(text: str, lines: tuple[str, ...]) -> tuple[tuple[tokenize.TokenInfo, ...] | None, SyntaxProblem | None]:
    """Tokenize ``text``; universal newlines split it, nothing is translated."""
    readline = io.StringIO(text, newline="").readline
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return tuple(tokenize.generate_tokens(readline)), None
    except SyntaxError as error:
        message = error.msg
        start = _clamp(lines, error.lineno or 1, error.offset or 1)
    except tokenize.TokenError as error:
        message, (line, column) = error.args
        start = _clamp(lines, line, column + 1)
    return None, SyntaxProblem(message, Span(start, start))


def _clamp(lines: tuple[str, ...], line: int, column: int) -> Position:
    """Return the position, kept inside the file (an EOF error may lie past it)."""
    last = max(len(lines), 1)
    if line > last:
        line, column = last, len(lines[-1]) + 1 if lines else 1
    return Position(max(line, 1), max(column, 1))


def _logical_ranges(tokens: tuple[tokenize.TokenInfo, ...]) -> tuple[tuple[int, int], ...]:
    """Return the line range of every logical line, in order."""
    ranges: list[tuple[int, int]] = []
    first: int | None = None
    for token in tokens:
        if token.type == tokenize.NEWLINE:
            if first is not None:
                ranges.append((first, token.start[0]))
            first = None
        elif first is None and token.type not in NOT_STATEMENT_TOKENS:
            first = token.start[0]
    return tuple(ranges)
