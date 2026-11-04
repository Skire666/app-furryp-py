"""Errors shown to the user as ``error: {message}``, with exit code 2."""

import difflib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

SUGGESTION_CUTOFF = 0.6
RULE = "rule"
RULE_OR_PREFIX = "rule or prefix"


class FurrypError(Exception):
    """Base class of the errors that end furryp with exit code 2."""


class UsageError(FurrypError):
    """Invalid command line: bad option, forbidden combination, unknown rule."""


class OptionError(UsageError):
    """Invalid value of a command-line option."""

    def __init__(self, option: str, problem: object) -> None:
        """Prefix the problem with the option."""
        super().__init__(f"{option}: {problem}")


class OptionConflictError(UsageError):
    """Two command-line options that cannot be used together (SPEC §4.3)."""

    def __init__(self, option: str, conflict: str) -> None:
        """Name both options."""
        super().__init__(f"{option} cannot be used with {conflict}")


class ConfigError(FurrypError):
    """Invalid or unreadable configuration file."""

    def __init__(self, path: str, problem: object) -> None:
        """Prefix the problem with the displayed path of the file."""
        super().__init__(f"{path}: {problem}")


class UnknownRuleError(FurrypError):
    """A rule code, prefix or name that matches no rule of the registry."""

    def __init__(self, hint: str, searched: str | None = None, kind: str = RULE) -> None:
        """Name the ``kind`` of what was searched and, if known, its value."""
        quoted = "" if searched is None else f' "{searched}"'
        super().__init__(f"unknown {kind}{quoted}{hint}")


class ReportWriteError(FurrypError):
    """The HTML report could not be written (SPEC §5.6)."""

    def __init__(self, path: Path, reason: str) -> None:
        """Name the report and say why it could not be written."""
        super().__init__(f"Failed to write report {path}: {reason}")


@dataclass(frozen=True, slots=True)
class FileFailure:
    """An internal error on a file: an exception in a rule or a measure (§4.4)."""

    path: Path
    reason: str


def format_suggestion(candidate: str) -> str:
    """Return the ``did you mean`` hint appended to an error message."""
    return f' (did you mean "{candidate}"?)'


def did_you_mean(word: str, candidates: Iterable[str]) -> str:
    """Return the hint for the candidate closest to ``word``, or ``""``.

    The comparison ignores case: ``fur`` suggests ``FUR``.
    """
    folded = {candidate.casefold(): candidate for candidate in candidates}
    matches = difflib.get_close_matches(word.casefold(), list(folded), n=1, cutoff=SUGGESTION_CUTOFF)
    return format_suggestion(folded[matches[0]]) if matches else ""
