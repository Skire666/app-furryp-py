"""Fix engine: applies the fixes of a file, then checks it again (SPEC §7.2).

Fixes are sorted by start; a fix that starts before the end of the last
retained one is left for the next pass, as in ruff. The edits are applied
from the end of the text to its start, then the text is checked again by
``lint.runner``, 10 passes at most. A pass that breaks the syntax of a file
that parsed is undone, and the fixes of the file stop there.

The text is written back only if it changed, with ``write_bytes`` in the
encoding read: encoding, BOM and line breaks are kept.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from furryp.core.diagnostic import Fix, apply_edits
from furryp.core.source import SourceFile, parse_source
from furryp.lint.runner import FileReport, Linter

MAX_PASSES = 10
NO_END = -1


@dataclass(frozen=True, slots=True)
class FixResult:
    """Fixes of a file: final report, text read and fixed text.

    ``original`` is ``None`` for a file that could not be read; ``fixed`` is
    the number of fixes applied and ``reverted`` tells that a pass broke the
    syntax and was undone.
    """

    report: FileReport
    original: SourceFile | None
    text: str
    fixed: int
    reverted: bool

    @property
    def text_read(self) -> str:
        """The text read (empty for a file that could not be read)."""
        return "" if self.original is None else self.original.text

    @property
    def changed(self) -> bool:
        """Whether the fixed text differs from the text read."""
        return self.original is not None and self.text != self.original.text


def _bounds(fix: Fix) -> tuple[int, int]:
    """Return the first and last text indexes touched by ``fix``."""
    return min(e.start for e in fix.edits), max(e.end for e in fix.edits)


def select_fixes(fixes: Iterable[Fix]) -> list[Fix]:
    """Return the fixes of a pass, sorted by start and without overlap."""
    selected: list[Fix] = []
    last_end = NO_END
    for fix in sorted(fixes, key=_bounds):
        start, end = _bounds(fix)
        if start > last_end:
            selected.append(fix)
            last_end = end
    return selected


def _apply_fixes(source: SourceFile, fixes: Iterable[Fix]) -> SourceFile:
    """Return the analysis of the text of ``source`` once ``fixes`` are applied."""
    text = apply_edits(source.text, (edit for fix in fixes for edit in fix.edits))
    return parse_source(source.path, source.display, text, source.encoding)


def fix_report(linter: Linter, report: FileReport) -> FixResult:
    """Apply the fixes of ``report`` until none is left (10 passes at most)."""
    original = report.source
    if original is None:
        return FixResult(report, None, "", 0, False)
    current, fixed = original, 0
    for _ in range(MAX_PASSES):
        fixes = select_fixes(d.fix for d in report.diagnostics if d.fix is not None)
        if not fixes:
            break
        candidate = _apply_fixes(current, fixes)
        if current.syntax_error is None and candidate.syntax_error is not None:
            return FixResult(report, original, current.text, fixed, True)
        current = candidate
        fixed += len(fixes)
        report = linter.check_source(current)
    return FixResult(report, original, current.text, fixed, False)


def fix_path(linter: Linter, path: Path) -> FixResult:
    """Read and check the file at ``path``, then fix it in memory."""
    return fix_report(linter, linter.check_path(path))


def write_source(source: SourceFile, text: str) -> None:
    """Write ``text`` over ``source`` in the encoding it was read with.

    ``utf-8-sig`` restores the BOM; the line breaks of ``text`` are written as they are, on every platform.
    """
    source.path.write_bytes(text.encode(source.encoding))


def write_fixes(result: FixResult) -> None:
    """Write the fixed text of a file, only if it changed."""
    if result.original is not None and result.changed:
        write_source(result.original, result.text)
