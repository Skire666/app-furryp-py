"""Typed configuration: global options and ``report`` options (SPEC §8.4)."""

import itertools
from dataclasses import dataclass, field

from furryp.config.defaults import (
    DEFAULT_EXCLUDE,
    DEFAULT_INCLUDE,
    DEFAULT_RATING_THRESHOLDS,
    DEFAULT_REPORT_TITLE,
    DEFAULT_SELECT,
    DEFAULT_TOP_N,
    RATING_MAX,
    RATING_MIN,
    RATING_THRESHOLD_COUNT,
)
from furryp.config.schema import CHECK_KEY
from furryp.core.discovery import FileFilter


def check_rating_thresholds(value: tuple[float, ...]) -> str | None:
    """Return the problem with ``report.rating-thresholds``, or ``None``."""
    in_range = all(RATING_MIN <= item <= RATING_MAX for item in value)
    increasing = all(low < high for low, high in itertools.pairwise(value))
    if len(value) == RATING_THRESHOLD_COUNT and in_range and increasing:
        return None
    return "expected 4 strictly increasing numbers between 0 and 1"


@dataclass(frozen=True, slots=True)
class ReportOptions:
    """Options of the HTML audit report."""

    top_n: int = DEFAULT_TOP_N
    title: str = DEFAULT_REPORT_TITLE
    rating_thresholds: tuple[float, ...] = field(
        default=DEFAULT_RATING_THRESHOLDS,
        metadata={CHECK_KEY: check_rating_thresholds},
    )


@dataclass(frozen=True, slots=True)
class Settings:
    """Effective configuration; ``rules`` maps a rule name to its options."""

    include: tuple[str, ...] = DEFAULT_INCLUDE
    exclude: tuple[str, ...] = DEFAULT_EXCLUDE
    extend_exclude: tuple[str, ...] = ()
    select: tuple[str, ...] = DEFAULT_SELECT
    extend_select: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()
    per_file_ignores: dict[str, tuple[str, ...]] = field(default_factory=dict)
    rules: dict[str, object] = field(default_factory=dict)
    report: ReportOptions = field(default_factory=ReportOptions)


def file_filter(settings: Settings) -> FileFilter:
    """Return the file filter of ``settings`` (``exclude`` ∪ ``extend-exclude``)."""
    return FileFilter(settings.include, settings.exclude + settings.extend_exclude)
