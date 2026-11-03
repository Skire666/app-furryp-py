"""Errors shown to the user as ``error: {message}``, with exit code 2."""

import difflib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

SUGGESTION_CUTOFF = 0.6


class FurrypError(Exception):
    """Base class of the errors that end furryp with exit code 2."""


class UsageError(FurrypError):
    """Invalid command line: bad option, forbidden combination, unknown rule."""


class ConfigError(FurrypError):
    """Invalid or unreadable configuration file."""


class UnknownRuleError(FurrypError):
    """A rule code, prefix or name that matches no rule of the registry."""


class ReportWriteError(FurrypError):
    """The HTML report could not be written (SPEC §5.6)."""


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
    matches = difflib.get_close_matches(
        word.casefold(), list(folded), n=1, cutoff=SUGGESTION_CUTOFF
    )
    return format_suggestion(folded[matches[0]]) if matches else ""
