"""Diagnostic data model (SPEC §9.2): positions, spans, fixes, diagnostics."""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

HELP_MAX_LENGTH = 160
ELLIPSIS = "…"
LINE_BREAKS = ("\n", "\r")


class InvalidHelpError(ValueError):
    """A help that is empty or on several lines: a defect of the rule."""

    def __init__(self, code: str) -> None:
        """Name the rule."""
        super().__init__(f"{code}: help must be one non-empty line")


@dataclass(frozen=True, slots=True, order=True)
class Position:
    """1-indexed line and 1-indexed column, counted in characters."""

    line: int
    column: int


@dataclass(frozen=True, slots=True)
class Span:
    """Range of a diagnostic, from ``start`` to ``end`` (excluded)."""

    start: Position
    end: Position


@dataclass(frozen=True, slots=True)
class Edit:
    """Replacement of ``text[start:end]`` by ``content`` (character indexes)."""

    start: int
    end: int
    content: str


@dataclass(frozen=True, slots=True)
class Fix:
    """Edits of a fix; every fix is safe (SPEC §7.1)."""

    edits: tuple[Edit, ...]


def apply_edits(text: str, edits: Iterable[Edit]) -> str:
    """Apply non-overlapping edits, from the end of the text to its start."""
    for edit in sorted(edits, key=lambda e: (e.start, e.end), reverse=True):
        text = text[: edit.start] + edit.content + text[edit.end :]
    return text


def line_span(line: int, start: int, end: int) -> Span:
    """Return the span of columns ``start`` to ``end`` (excluded) of ``line``."""
    return Span(Position(line, start), Position(line, end))


# The empty span of a whole file: it has no excerpt, like ``0..0`` in ruff.
FILE_START = line_span(1, 1, 1)


def truncate(text: str, limit: int) -> str:
    """Return ``text`` cut to ``limit`` characters, ``…`` included."""
    if len(text) <= limit:
        return text
    return text[: limit - len(ELLIPSIS)] + ELLIPSIS


def fit_help(text: str) -> str:
    """Return ``text`` truncated to 160 characters with ``…`` (SPEC §11.0)."""
    return truncate(text, HELP_MAX_LENGTH)


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """A violation of a rule; ``help`` is mandatory, on a single line."""

    code: str
    name: str
    message: str
    path: Path
    span: Span
    help: str
    fix: Fix | None = None

    def __post_init__(self) -> None:
        """Refuse an empty or multi-line help; truncate a long one."""
        if not self.help.strip() or any(brk in self.help for brk in LINE_BREAKS):
            raise InvalidHelpError(self.code)
        object.__setattr__(self, "help", fit_help(self.help))
