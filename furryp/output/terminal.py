"""Terminal output of ``furryp check``, in the format of ruff (SPEC §5.1, §5.2).

Diagnostics are sorted by displayed path, line, column and code, separated by
a blank line and followed by the footer. A source that cannot be read or
decoded, or a diagnostic on the whole file, is rendered without gutter nor
excerpt; no line number is shown, so the arrow has no indentation (``W`` = 0),
as in ruff. A fix is shown below the help, as a diff.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from furryp.core.diagnostic import FILE_START, Diagnostic
from furryp.core.paths import display_path
from furryp.core.source import SourceFile
from furryp.lint.runner import FileReport
from furryp.output.fix_preview import render_fix
from furryp.output.snippet import build_snippet

ALL_CHECKS_PASSED = "All checks passed!"
FOUND = "Found {count} error{plural}."
FOUND_AFTER_FIX = "Found {total} error{plural} ({fixed} fixed, {remaining} remaining)."
FIXABLE = "[*] {count} fixable with `--fix`."
FIX_MARKER = " [*]"
ARROW = "--> "
BLOCK_SEPARATOR = "\n\n"


@dataclass(frozen=True, slots=True)
class Entry:
    """A diagnostic to display, with its displayed path and its source."""

    display: str
    diagnostic: Diagnostic
    source: SourceFile | None

    def sort_key(self) -> tuple[str, int, int, str]:
        """Order of display: path, line, column, code (SPEC §5.1, rule 11)."""
        start = self.diagnostic.span.start
        return (self.display, start.line, start.column, self.diagnostic.code)


def collect_entries(reports: Iterable[FileReport], cwd: Path) -> list[Entry]:
    """Return the diagnostics of ``reports`` in display order."""
    entries = [
        Entry(display_path(report.path, cwd), diagnostic, report.source)
        for report in reports
        for diagnostic in report.diagnostics
    ]
    return sorted(entries, key=Entry.sort_key)


def plural(count: int) -> str:
    """Return ``"s"`` unless ``count`` is 1."""
    return "" if count == 1 else "s"


def render_header(diagnostic: Diagnostic) -> str:
    """Return ``{name} [{code}]: {message}``, with `` [*]`` if fixable."""
    marker = FIX_MARKER if diagnostic.fix is not None else ""
    return f"{diagnostic.name} [{diagnostic.code}]{marker}: {diagnostic.message}"


def render_entry(entry: Entry) -> str:
    """Return the block of a diagnostic: header, arrow, excerpt, help and the diff of its fix."""
    diagnostic, source = entry.diagnostic, entry.source
    start = diagnostic.span.start
    location = f"{entry.display}:{start.line}:{start.column}"
    if source is None or diagnostic.span == FILE_START:
        width, excerpt = 0, ()
    else:
        snippet = build_snippet(source.lines, diagnostic.span)
        width, excerpt = snippet.width, snippet.lines
    preview = ()
    if source is not None and diagnostic.fix is not None:
        preview = render_fix(source.text, diagnostic.fix)
    arrow = " " * width + ARROW + location
    return "\n".join((render_header(diagnostic), arrow, *excerpt, f"help: {diagnostic.help}", *preview))


def render_total(remaining: int, fixed: int) -> str:
    """Return the ``Found {n} error{s}.`` line.

    It has the fixed and remaining counts after ``--fix`` when at least one fix was applied (as ruff).
    """
    total = remaining + fixed
    if not fixed:
        return FOUND.format(count=total, plural=plural(total))
    return FOUND_AFTER_FIX.format(total=total, plural=plural(total), fixed=fixed, remaining=remaining)


def render_footer(diagnostics: Sequence[Diagnostic], fixed: int = 0) -> str:
    """Return the footer: total, then the number of fixable diagnostics.

    After ``--fix``, ``diagnostics`` are the remaining ones and ``fixed`` the
    number of fixes applied.
    """
    if not diagnostics and not fixed:
        return ALL_CHECKS_PASSED
    lines = [render_total(len(diagnostics), fixed)]
    fixable = sum(diagnostic.fix is not None for diagnostic in diagnostics)
    if fixable:
        lines.append(FIXABLE.format(count=fixable))
    return "\n".join(lines)


def render_check(entries: Sequence[Entry], fixed: int = 0) -> str:
    """Return the full output of ``furryp check`` for sorted ``entries``.

    After ``--fix``, ``entries`` are the remaining diagnostics and ``fixed``
    the number of fixes applied.
    """
    blocks = [render_entry(entry) for entry in entries]
    blocks.append(render_footer([entry.diagnostic for entry in entries], fixed))
    return BLOCK_SEPARATOR.join(blocks)
