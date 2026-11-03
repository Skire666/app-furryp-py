"""Source excerpt of a diagnostic, as ruff 0.17.3 renders it (SPEC §5.1).

``W`` is the number of digits of the largest line number shown. Context is 2
lines before the start and after the end of the span, bounded to the file, then
the blank lines at both ends of the window are removed.

Tabs are shown as 4 spaces, and other invisible characters as ruff shows them:
control pictures, the replacement character for bidirectional controls, nothing
for a zero width joiner. The underline follows the columns taken in a terminal:
2 for a wide character, 0 for a combining mark or a format character.

A span on several lines is drawn in a margin of 2 characters: ``/`` on its first
line if only blanks precede it, else a line of ``_`` up to its start; ``|`` on
the next lines; then a line of ``_`` up to its last character. The closing
gutter only follows a line of source, not an underline.
"""

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from furryp.core.diagnostic import Span

CONTEXT_LINES = 2
CONTROL_PICTURES = 0x2400
BIDIRECTIONAL_CONTROLS = "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
SHOWN_CHARACTERS = str.maketrans(
    {
        **{chr(code): chr(CONTROL_PICTURES + code) for code in range(0x20)},
        "\t": "    ",
        "\x7f": "\u2421",
        "\u200d": None,
        **dict.fromkeys(BIDIRECTIONAL_CONTROLS, "\ufffd"),
    }
)
ZERO_WIDTH_CATEGORIES = frozenset({"Mn", "Me", "Cf"})
WIDE_CLASSES = frozenset({"W", "F"})
GUTTER = "|"
CARET = "^"
OPEN_LINE = "_"
MARGIN_OPEN = "/"
MARGIN_LINE = "|"


@dataclass(frozen=True, slots=True)
class Snippet:
    """Rendered excerpt: gutter width ``W`` and lines, gutter to gutter."""

    width: int
    lines: tuple[str, ...]


def gutter(width: int) -> str:
    """Return the empty gutter line of a snippet of width ``width``."""
    return " " * (width + 1) + GUTTER


def _shown(text: str) -> str:
    """Return ``text`` as an excerpt shows it."""
    return text.translate(SHOWN_CHARACTERS)


def _char_width(char: str) -> int:
    """Return the columns that ``char`` takes in a terminal."""
    if unicodedata.category(char) in ZERO_WIDTH_CATEGORIES:
        return 0
    return 2 if unicodedata.east_asian_width(char) in WIDE_CLASSES else 1


def display_width(text: str) -> int:
    """Return the columns that ``text`` takes in a terminal."""
    return sum(_char_width(char) for char in text)


def _shown_width(text: str) -> int:
    """Return the columns that ``text`` takes once shown in an excerpt."""
    return display_width(_shown(text))


def _line_text(lines: Sequence[str], number: int) -> str:
    """Return the text of line ``number``; a line past the end is empty."""
    return lines[number - 1] if number <= len(lines) else ""


def _window(lines: Sequence[str], start: int, end: int) -> list[int]:
    """Return the line numbers shown around lines ``start`` to ``end``."""
    last = min(max(len(lines), end), end + CONTEXT_LINES)
    numbers = list(range(max(1, start - CONTEXT_LINES), last + 1))
    while numbers[0] < start and not _line_text(lines, numbers[0]).strip():
        numbers.pop(0)
    while numbers[-1] > end and not _line_text(lines, numbers[-1]).strip():
        numbers.pop()
    return numbers


def _source_line(number: int, width: int, margin: str, text: str) -> str:
    """Return a line of source, without trailing blanks if it is empty."""
    shown = margin + _shown(text) if text else margin.rstrip()
    return f"{number:>{width}} {GUTTER}" + (f" {shown}" if shown else "")


def _underline(text: str, span: Span, width: int) -> str:
    """Return the caret line under the line ``text`` of a span on one line."""
    start, end = span.start, span.end
    first = start.column - 1
    indent = _shown_width(text[:first])
    length = max(_shown_width(text[first : end.column - 1]), 1)
    return gutter(width) + " " + " " * indent + CARET * length


def _single_line(
    lines: Sequence[str], numbers: Sequence[int], span: Span, width: int
) -> list[str]:
    """Return the lines of an excerpt whose span holds on one line."""
    rendered: list[str] = []
    for number in numbers:
        text = _line_text(lines, number)
        rendered.append(_source_line(number, width, "", text))
        if number == span.start.line:
            rendered.append(_underline(text, span, width))
    return rendered


def _opening(text: str, span: Span, width: int) -> str:
    """Return the line of ``_`` up to the start of a span on several lines."""
    indent = _shown_width(text[: span.start.column - 1])
    return gutter(width) + "  " + OPEN_LINE * (indent + 1) + CARET


def _closing(text: str, span: Span, width: int) -> str:
    """Return the line of ``_`` up to the last character of such a span."""
    last = max(span.end.column - 2, 0)
    indent = _shown_width(text[:last])
    return gutter(width) + " " + MARGIN_LINE + OPEN_LINE * (indent + 1) + CARET


def _margin(number: int, span: Span, opens_at_start: bool) -> str:
    """Return the 2 characters drawn before the line ``number`` of a span."""
    if number == span.start.line and opens_at_start:
        return MARGIN_OPEN + " "
    if span.start.line < number <= span.end.line:
        return MARGIN_LINE + " "
    return "  "


def _several_lines(
    lines: Sequence[str], numbers: Sequence[int], span: Span, width: int
) -> list[str]:
    """Return the lines of an excerpt whose span holds on several lines."""
    first_text = _line_text(lines, span.start.line)
    opens_at_start = not first_text[: span.start.column - 1].strip()
    rendered: list[str] = []
    for number in numbers:
        text = _line_text(lines, number)
        margin = _margin(number, span, opens_at_start)
        rendered.append(_source_line(number, width, margin, text))
        if number == span.start.line and not opens_at_start:
            rendered.append(_opening(text, span, width))
        if number == span.end.line:
            rendered.append(_closing(text, span, width))
    return rendered


def build_snippet(lines: Sequence[str], span: Span) -> Snippet:
    """Return the excerpt of ``lines`` around ``span``."""
    start, end = span.start.line, span.end.line
    numbers = _window(lines, start, end)
    width = len(str(numbers[-1]))
    draw = _single_line if start == end else _several_lines
    rendered = [gutter(width), *draw(lines, numbers, span, width)]
    if numbers[-1] > end:
        rendered.append(gutter(width))
    return Snippet(width, tuple(rendered))
