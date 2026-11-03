"""What the report keeps of each checked file (SPEC §12.1).

A file is summarized as soon as it is checked, inside the error handling per file
of the command line: an exception in a measure only loses that file. The source,
the tree and the tokens are not kept. The measures are read for every file,
whatever the selection of rules; the violations respect the selection,
``per-file-ignores`` and ``foqa``.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from furryp.core.diagnostic import Diagnostic
from furryp.core.paths import display_path
from furryp.lint.runner import FileReport, Linter
from furryp.metrics.classes import ClassMetrics
from furryp.metrics.file_metrics import FunctionMetrics
from furryp.metrics.halstead import Halstead
from furryp.rules.syntax import INVALID_SYNTAX


@dataclass(frozen=True, slots=True)
class AnalysisError:
    """Why a file has no measures: FUR000, or an internal error without a code."""

    path: str
    location: str | None
    code: str | None
    message: str


@dataclass(frozen=True, slots=True)
class FailedFile:
    """A file left out of the aggregates; ``violations`` is its whole count of
    diagnostics, which still decides the exit code."""

    errors: tuple[AnalysisError, ...]
    violations: int


@dataclass(frozen=True, slots=True)
class FileSummary:
    """The measures of a file, and its diagnostics counted per rule code."""

    path: str
    lines: int
    code_lines: int
    functions: tuple[FunctionMetrics, ...]
    classes: tuple[ClassMetrics, ...]
    halstead: Halstead
    violations: Counter[str]
    suppressed: Counter[str]
    fixable: Counter[str]

    def count_of(self, codes: Iterable[str]) -> int:
        """Return the number of violations of the rules ``codes`` in this file."""
        return sum(self.violations[code] for code in codes)

    @property
    def outer_functions(self) -> tuple[FunctionMetrics, ...]:
        """The functions evaluated alone by FUR203: not the nested ones (A13)."""
        return tuple(item for item in self.functions if not item.nested)


def _analysis_error(path: str, diagnostic: Diagnostic) -> AnalysisError:
    """Return the entry of a FUR000 diagnostic."""
    start = diagnostic.span.start
    location = f"{start.line}:{start.column}"
    return AnalysisError(path, location, diagnostic.code, diagnostic.message)


def summarize(report: FileReport, cwd: Path) -> FileSummary | FailedFile:
    """Return what the report keeps of a checked file, measures computed."""
    path = display_path(report.path, cwd)
    errors = tuple(
        _analysis_error(path, diagnostic)
        for diagnostic in report.diagnostics
        if diagnostic.code == INVALID_SYNTAX.code
    )
    metrics = report.metrics
    if errors or metrics is None:
        return FailedFile(errors, len(report.diagnostics))
    return FileSummary(
        path,
        metrics.lines,
        metrics.code_lines,
        metrics.functions,
        metrics.classes,
        metrics.halstead,
        Counter(item.code for item in report.diagnostics),
        Counter(item.code for item in report.suppressed),
        Counter(item.code for item in report.diagnostics if item.fix is not None),
    )


def summarize_path(linter: Linter, cwd: Path, path: Path) -> FileSummary | FailedFile:
    """Check the file at ``path``, then summarize it."""
    return summarize(linter.check_path(path), cwd)
