"""Diff of a fix, shown below the help of a diagnostic, as ruff 0.17.3 (SPEC §5.1).

Lines are compared whole, each change keeping one line of context. Line numbers
are those of the fixed text, aligned to the left; a removed line has none. More
than 4 equal lines between two changes are cut by a line of dashes. Tabs stay tabs,
unlike in the excerpt, and fewer control characters are replaced than there.

A fix is local: the lines that both texts share at their start and at their end
are left out of the comparison, whose cost grows fast with the number of lines.
"""

import difflib
from collections.abc import Iterator, Sequence

from furryp.core.diagnostic import Fix, apply_edits
from furryp.core.positions import split_lines_with_breaks
from furryp.output.snippet import gutter

CONTEXT_LINES = 1
MAX_EQUAL_LINES_SHOWN = 4
HUNK_SEPARATOR = "-" * 80
SHOWN_CHARACTERS = str.maketrans(
    {"\x07": "\u2407", "\x08": "\u2408", "\x1b": "\u241b", "\x7f": "\u2421"}
)
REMOVED = "-"
ADDED = "+"
KEPT = "|"
LINE_BREAK_CHARACTERS = "\r\n"
EQUAL = "equal"

type Opcode = tuple[str, int, int, int, int]


def _line(label: str, width: int, sign: str, text: str) -> str:
    """Return a line of the diff, without trailing blanks if it is empty."""
    content = text.rstrip(LINE_BREAK_CHARACTERS).translate(SHOWN_CHARACTERS)
    return f"{label:<{width}} {sign}" + (f" {content}" if content else "")


def _new_lines(
    after: Sequence[str], first: int, last: int, width: int, sign: str
) -> Iterator[str]:
    """Yield the lines ``first`` to ``last`` of the fixed text, with their numbers."""
    for number in range(first, last):
        yield _line(str(number + 1), width, sign, after[number])


def _hunk_lines(
    hunk: Sequence[Opcode], before: Sequence[str], after: Sequence[str], width: int
) -> Iterator[str]:
    """Yield the lines of a group of changes: what is removed, then what is added."""
    for tag, first, last, new_first, new_last in hunk:
        if tag == EQUAL:
            yield from _new_lines(after, new_first, new_last, width, KEPT)
        else:
            for text in before[first:last]:
                yield _line("", width, REMOVED, text)
            yield from _new_lines(after, new_first, new_last, width, ADDED)


def _common_ends(before: Sequence[str], after: Sequence[str]) -> tuple[int, int]:
    """Return how many lines both texts share at their start and at their end."""
    limit = min(len(before), len(after))
    start = 0
    while start < limit and before[start] == after[start]:
        start += 1
    end = 0
    while end < limit - start and before[-end - 1] == after[-end - 1]:
        end += 1
    return start, end


def _opcodes(before: Sequence[str], after: Sequence[str]) -> list[Opcode]:
    """Return the changes between two whole texts, the shared ends included."""
    start, end = _common_ends(before, after)
    matcher = difflib.SequenceMatcher(
        None,
        before[start : len(before) - end],
        after[start : len(after) - end],
        autojunk=False,
    )
    opcodes = [(EQUAL, 0, start, 0, start)] if start else []
    opcodes += [
        (tag, a + start, b + start, c + start, d + start)
        for tag, a, b, c, d in matcher.get_opcodes()
    ]
    if end:
        opcodes.append(
            (EQUAL, len(before) - end, len(before), len(after) - end, len(after))
        )
    return opcodes


def _hunks(opcodes: Sequence[Opcode]) -> list[list[Opcode]]:
    """Return the groups of changes, each keeping its lines of context; a run of
    equal lines too long to be shown whole ends a group."""
    hunks: list[list[Opcode]] = []
    current: list[Opcode] = []
    for index, opcode in enumerate(opcodes):
        tag, first, last, new_first, new_last = opcode
        if tag != EQUAL:
            current.append(opcode)
        elif last - first > MAX_EQUAL_LINES_SHOWN or index in (0, len(opcodes) - 1):
            if current:
                keep = min(CONTEXT_LINES, last - first)
                current.append(
                    (EQUAL, first, first + keep, new_first, new_first + keep)
                )
                hunks.append(current)
            keep = min(CONTEXT_LINES, last - first)
            current = [(EQUAL, last - keep, last, new_last - keep, new_last)]
        else:
            current.append(opcode)
    has_change = any(opcode[0] != EQUAL for opcode in current)
    return [*hunks, current] if has_change else hunks


def render_fix(text: str, fix: Fix) -> tuple[str, ...]:
    """Return the lines of the diff of ``fix`` on ``text``, empty if it changes
    nothing."""
    before = split_lines_with_breaks(text)
    after = split_lines_with_breaks(apply_edits(text, fix.edits))
    hunks = _hunks(_opcodes(before, after))
    if not hunks:
        return ()
    width = len(str(hunks[-1][-1][4]))
    frame = gutter(width)
    lines = [frame]
    for index, hunk in enumerate(hunks):
        if index:
            lines.append(HUNK_SEPARATOR)
        lines.extend(_hunk_lines(hunk, before, after, width))
    lines.append(frame)
    return tuple(lines)
