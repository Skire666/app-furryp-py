"""Lines, character columns and text indexes (SPEC §10.1, §10.4).

``ast`` gives columns in UTF-8 bytes, ``tokenize`` in characters. furryp
displays 1-indexed lines and character columns, and edits the text with
character indexes: every conversion goes through this module.
"""

import bisect
import re
from dataclasses import dataclass

from furryp.core.diagnostic import Position

LINE_BREAK = re.compile(r"\r\n|\r|\n")
UTF8 = "utf-8"


def split_lines(text: str) -> tuple[str, ...]:
    """Return the physical lines of ``text``, without their line breaks.

    Only ``\\r\\n``, ``\\r`` and ``\\n`` end a line, unlike ``str.splitlines``
    which also splits on ``\\f``, ``\\v``, ``\\x1c``… A final line break does
    not start a new line.
    """
    if not text:
        return ()
    lines = LINE_BREAK.split(text)
    if not lines[-1]:
        lines.pop()
    return tuple(lines)


def split_lines_with_breaks(text: str) -> tuple[str, ...]:
    """Return the physical lines of ``text``, each with its own line break.

    The last line has no line break if the text does not end with one.
    """
    lines: list[str] = []
    start = 0
    for match in LINE_BREAK.finditer(text):
        lines.append(text[start : match.end()])
        start = match.end()
    if start < len(text):
        lines.append(text[start:])
    return tuple(lines)


def first_line_break(text: str) -> str | None:
    """Return the first line break of ``text`` (``\\r\\n``, ``\\r`` or ``\\n``)."""
    match = LINE_BREAK.search(text)
    return None if match is None else match.group()


def byte_to_char_column(line: str, byte_column: int) -> int:
    """Convert a 0-indexed UTF-8 byte column of ``line`` (``ast``) to characters."""
    return len(line.encode(UTF8)[:byte_column].decode(UTF8, errors="ignore"))


def char_to_byte_column(line: str, char_column: int) -> int:
    """Convert a 0-indexed character column of ``line`` to UTF-8 bytes."""
    return len(line[:char_column].encode(UTF8))


@dataclass(frozen=True, slots=True)
class TextIndex:
    """Start index of every line of a text: line and column ↔ text index."""

    starts: tuple[int, ...]

    def index(self, position: Position) -> int:
        """Return the text index of a 1-indexed line and character column."""
        return self.starts[position.line - 1] + position.column - 1

    def position(self, index: int) -> Position:
        """Return the 1-indexed line and character column of a text index."""
        line = bisect.bisect_right(self.starts, index)
        return Position(line, index - self.starts[line - 1] + 1)


def text_index(text: str) -> TextIndex:
    """Return the index of ``text``; a final line break starts an empty line."""
    starts = (0, *(match.end() for match in LINE_BREAK.finditer(text)))
    return TextIndex(starts)
