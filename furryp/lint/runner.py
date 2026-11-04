"""Linting of one file: selected rules, ``foqa`` filter, then FUR001 (§9.3).

The names imported by the module (``ImportTable``) are read once per file and
shared by the rules. So are the metrics (``FileMetrics``), computed on first use.
The project (``ProjectContext``) is built once per run.

A warning about a directive goes to ``warn`` as soon as the file is read, as ruff
prints it: the fix engine reads a file at each pass, and so warns again.

On a file that does not tokenize or parse, only the textual rules run, and
FUR001 is not evaluated: the other rules did not run, so every directive would
look unused. FUR000 and FUR001 are never suppressed.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from furryp.config.options import Settings
from furryp.config.selection import file_selection
from furryp.core.diagnostic import Diagnostic
from furryp.core.discovery import relative_to_root
from furryp.core.names import import_table
from furryp.core.paths import display_path
from furryp.core.registry import Registry, RuleContext
from furryp.core.source import (
    SourceDecodeError,
    SourceFile,
    SourceReadError,
    read_source,
)
from furryp.core.suppression import Suppressions, scan_directives
from furryp.metrics.file_metrics import FileMetrics
from furryp.rules.contracts import project_context
from furryp.rules.suppression import UNUSED_FOQA, unused_foqa
from furryp.rules.syntax import INVALID_SYNTAX, decode_failure, read_failure

UNSUPPRESSIBLE = frozenset({INVALID_SYNTAX.code, UNUSED_FOQA.code})


@dataclass(frozen=True, slots=True)
class FileReport:
    """Result of a file.

    Its source (``None`` if unreadable), its diagnostics and its metrics (``None`` without a source), computed on first use.
    """

    path: Path
    source: SourceFile | None
    diagnostics: tuple[Diagnostic, ...]
    suppressed: tuple[Diagnostic, ...]
    metrics: FileMetrics | None = None

    @property
    def lines(self) -> tuple[str, ...] | None:
        """The lines of the source, or ``None`` if it could not be read."""
        return None if self.source is None else self.source.lines


def ignore_warning(message: str) -> None:
    """Default of ``Linter.warn``: the warnings of a directive are not shown."""


class Linter:
    """Checks files with the rules of a registry and the effective settings."""

    def __init__(
        self,
        registry: Registry,
        settings: Settings,
        root: Path,
        cwd: Path,
        warn: Callable[[str], None] = ignore_warning,
    ) -> None:
        self._registry = registry
        self._settings = settings
        self._root = root
        self._cwd = cwd
        self._warn = warn
        self._project = project_context(root, settings.rules)

    @property
    def registry(self) -> Registry:
        """The registry of the rules."""
        return self._registry

    def check_path(self, path: Path) -> FileReport:
        """Read and check the file at ``path`` (absolute and resolved)."""
        try:
            source = read_source(path, display_path(path, self._cwd))
        except SourceReadError as error:
            return FileReport(path, None, (read_failure(path, str(error)),), ())
        except SourceDecodeError as error:
            return FileReport(path, None, (decode_failure(path, str(error)),), ())
        return self.check_source(source)

    def check_source(self, source: SourceFile) -> FileReport:
        """Check a source: rules, then the ``foqa`` filter, then FUR001."""
        relative = relative_to_root(source.path, self._root)
        selected = file_selection(self._settings, self._registry, relative)
        suppressions = self._suppressions(source)
        metrics = FileMetrics(source)
        kept: list[Diagnostic] = []
        suppressed: list[Diagnostic] = []
        for diagnostic in self._run_rules(source, selected, metrics):
            unsuppressible = diagnostic.code in UNSUPPRESSIBLE
            if unsuppressible or not suppressions.suppresses(diagnostic):
                kept.append(diagnostic)
            else:
                suppressed.append(diagnostic)
        if UNUSED_FOQA.code in selected and source.syntax_error is None:
            kept += unused_foqa(suppressions, self._registry, selected, source)
        return FileReport(source.path, source, tuple(kept), tuple(suppressed), metrics)

    def _suppressions(self, source: SourceFile) -> Suppressions:
        """Read the directives of a source and report the warnings about them."""
        scan = scan_directives(source, self._registry)
        for warning in scan.warnings:
            self._warn(warning)
        return Suppressions(scan.directives, self._registry)

    def _run_rules(
        self, source: SourceFile, selected: frozenset[str], metrics: FileMetrics
    ) -> list[Diagnostic]:
        """Return the diagnostics of the selected rules, in rule order."""
        diagnostics: list[Diagnostic] = []
        imports = import_table(source.tree)
        for rule in self._registry.rules:
            if rule.code not in selected:
                continue
            if rule.textual or source.syntax_error is None:
                options = self._settings.rules.get(rule.name)
                context = RuleContext(source, options, imports, metrics, self._project)
                diagnostics.extend(rule.check(context))
        return diagnostics
