"""Model of the HTML audit report, built from the checked files (SPEC §12).

The files without measures (FUR000, internal error) are left out of the aggregates
and listed apart, so that no file disappears from the report without a trace. The
whole count of diagnostics is kept for the exit code, which is the one of ``check``.
"""

import platform
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from furryp import __version__
from furryp.config.loader import Configuration
from furryp.config.schema import settings_json
from furryp.config.selection import active_rules
from furryp.core.errors import FileFailure
from furryp.core.paths import display_path
from furryp.core.registry import Registry
from furryp.report.categories import Category, build_categories
from furryp.report.files import AnalysisError, FailedFile, FileSummary
from furryp.rules.suppression import UNUSED_FOQA

TIME_PRECISION = "seconds"
DENSITY_BASE = 1000

type Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class Timing:
    """When the analysis started and finished, read on the same clock."""

    started: datetime
    finished: datetime


@dataclass(frozen=True, slots=True)
class Header:
    """The head of the report."""

    title: str
    generated_at: str
    furryp_version: str
    python_version: str
    project_root: str
    config_file: str | None
    active_rules: int
    duration: float


@dataclass(frozen=True, slots=True)
class Summary:
    """The cards of the summary."""

    files: int
    files_in_error: int
    lines: int
    code_lines: int
    functions: int
    classes: int
    violations: int
    density: float | None
    suppressed: int
    unused_foqa: int | None
    fixable: int


@dataclass(frozen=True, slots=True)
class ReportModel:
    """Everything the report shows; ``total_violations`` decides the exit code."""

    header: Header
    summary: Summary
    categories: tuple[Category, ...]
    errors: tuple[AnalysisError, ...]
    configuration: str
    total_violations: int


def _header(configuration: Configuration, active: frozenset[str], timing: Timing) -> Header:
    """Return the head of the report."""
    config_file = configuration.config_file
    elapsed = (timing.finished - timing.started).total_seconds()
    return Header(
        title=configuration.settings.report.title,
        generated_at=timing.started.isoformat(timespec=TIME_PRECISION),
        furryp_version=__version__,
        python_version=platform.python_version(),
        project_root=str(configuration.project_root),
        config_file=None if config_file is None else str(config_file),
        active_rules=len(active),
        duration=max(elapsed, 0.0),
    )


def _summary(files: Sequence[FileSummary], in_error: int, active: frozenset[str]) -> Summary:
    """Return the cards of the summary.

    The files in error are only counted, and the unused directives are unknown if FUR001 did not run.
    """
    code_lines = sum(file.code_lines for file in files)
    violations = sum(file.violations.total() for file in files)
    unused = sum(file.violations[UNUSED_FOQA.code] for file in files)
    return Summary(
        files=len(files),
        files_in_error=in_error,
        lines=sum(file.lines for file in files),
        code_lines=code_lines,
        functions=sum(len(file.functions) for file in files),
        classes=sum(len(file.classes) for file in files),
        violations=violations,
        density=violations / code_lines * DENSITY_BASE if code_lines else None,
        suppressed=sum(file.suppressed.total() for file in files),
        unused_foqa=unused if UNUSED_FOQA.code in active else None,
        fixable=sum(file.fixable.total() for file in files),
    )


def _error_order(error: AnalysisError) -> str:
    """Return the sort key of an analysis error: its path."""
    return error.path


def _analysis_errors(
    failed: Sequence[FailedFile], failures: Sequence[FileFailure], cwd: Path
) -> tuple[AnalysisError, ...]:
    """Return every file without measures, sorted by path; the list is complete."""
    errors = [error for file in failed for error in file.errors]
    errors += [AnalysisError(display_path(failure.path, cwd), None, None, failure.reason) for failure in failures]
    return tuple(sorted(errors, key=_error_order))


def build_report(
    configuration: Configuration,
    registry: Registry,
    results: Sequence[FileSummary | FailedFile],
    failures: Sequence[FileFailure],
    cwd: Path,
    timing: Timing,
) -> ReportModel:
    """Return the model of the report; same input, same model (§12.2)."""
    files = [item for item in results if isinstance(item, FileSummary)]
    failed = [item for item in results if isinstance(item, FailedFile)]
    settings = configuration.settings
    active = active_rules(settings, registry)
    summary = _summary(files, len(failed) + len(failures), active)
    return ReportModel(
        _header(configuration, active, timing),
        summary,
        build_categories(files, settings, registry),
        _analysis_errors(failed, failures, cwd),
        settings_json(settings),
        summary.violations + sum(item.violations for item in failed),
    )
