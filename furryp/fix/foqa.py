"""``--add-foqa``: freeze the existing violations with directives (SPEC §6.1).

Every remaining diagnostic, except FUR000 and FUR001, gets a directive in the
compact format (``  # foqa:FUR101,FUR403``, codes sorted). A rule of scope
``line`` is frozen at the end of the last physical line of its logical line;
the codes are merged into a directive already there, and nothing is added
under a blanket ``# foqa``. A rule of scope ``file`` goes to a single
``# furryp: foqa:CODES`` line, after the shebang and the coding declaration.

Files in FUR000 are left alone: without tokens, an added directive would not
be seen, and a second run would add it again. The text is written as the fix
engine writes it.
"""

import re
from collections.abc import Iterable, Sequence
from pathlib import Path

from furryp.core.diagnostic import Diagnostic, Edit
from furryp.core.registry import Registry, Scope
from furryp.core.source import SourceFile
from furryp.core.suppression import Directive, DirectiveKind, find_directives, format_directive
from furryp.fix.engine import apply_edits, write_source
from furryp.lint.runner import UNSUPPRESSIBLE, Linter
from furryp.output.terminal import plural

DIRECTIVE_SPACING = "  "
ADDED = "Added {count} foqa directive{plural}."
SHEBANG = "#!"
CODING_DECLARATION = re.compile(r"^[ \t\f]*#.*?coding[:=][ \t]*[-\w.]+", re.ASCII)
CODING_LINES = 2


def preamble_end(lines: Sequence[str]) -> int:
    """Return the number of lines taken by the shebang and coding declaration."""
    end = 1 if lines and lines[0].startswith(SHEBANG) else 0
    for number in range(end, min(CODING_LINES, len(lines))):
        if CODING_DECLARATION.match(lines[number]):
            end = number + 1
    return end


def _line_end_to_add(source: SourceFile, line: int) -> str:
    """Return the line break that an edited ``line`` lacks, as ``--add-noqa`` adds it.

    Only the last line of a file can lack one.
    """
    start, following = source.line_bounds(line)
    return "" if start + len(source.lines[line - 1]) < following else source.newline


def merge_edit(source: SourceFile, directive: Directive, codes: Iterable[str]) -> Edit:
    """Return the edit rewriting ``directive`` with ``codes`` added, sorted."""
    start = source.index.index(directive.span.start)
    end = source.index.index(directive.span.end)
    identifiers = sorted((*directive.identifiers, *codes))
    content = format_directive(directive.kind, identifiers)
    line_end = _line_end_to_add(source, directive.span.start.line)
    if line_end:
        return Edit(start, len(source.text), content + source.text[end:] + line_end)
    return Edit(start, end, content)


def append_edit(source: SourceFile, line: int, codes: Iterable[str]) -> Edit:
    """Return the edit ending ``line`` with a directive, trailing blanks removed."""
    start = source.line_bounds(line)[0]
    text = source.lines[line - 1]
    directive = format_directive(DirectiveKind.LINE, sorted(codes))
    content = DIRECTIVE_SPACING + directive + _line_end_to_add(source, line)
    return Edit(start + len(text.rstrip()), start + len(text), content)


def insert_edit(source: SourceFile, codes: Iterable[str]) -> Edit:
    """Return the edit inserting a file directive line after the preamble."""
    line = preamble_end(source.lines)
    directive = format_directive(DirectiveKind.FILE, sorted(codes))
    newline = source.newline
    if line < len(source.index.starts):
        start = source.index.starts[line]
        return Edit(start, start, directive + newline)
    end = len(source.text)
    return Edit(end, end, newline + directive + newline)


def line_edit(
    source: SourceFile, directives: Sequence[Directive], lines: tuple[int, int], codes: set[str]
) -> Edit | None:
    """Return the edit freezing ``codes`` on the logical line ``lines``."""
    present = [
        directive
        for directive in directives
        if directive.kind is DirectiveKind.LINE and (directive.first_line, directive.last_line) == lines
    ]
    if any(not directive.identifiers for directive in present):
        return None
    if present:
        return merge_edit(source, present[-1], codes)
    return append_edit(source, lines[1], codes)


def file_edit(source: SourceFile, directives: Sequence[Directive], codes: set[str]) -> Edit | None:
    """Return the edit freezing ``codes`` in the single file directive."""
    present = [d for d in directives if d.kind is DirectiveKind.FILE]
    if any(not directive.identifiers for directive in present):
        return None
    if present:
        return merge_edit(source, present[0], codes)
    return insert_edit(source, codes)


def _codes_to_freeze(
    source: SourceFile, registry: Registry, diagnostics: Iterable[Diagnostic]
) -> tuple[dict[tuple[int, int], set[str]], set[str]]:
    """Return the codes to freeze per logical line, and those of the file."""
    by_line: dict[tuple[int, int], set[str]] = {}
    file_codes: set[str] = set()
    for diagnostic in diagnostics:
        rule = registry.find(diagnostic.code)
        if rule is None or diagnostic.code in UNSUPPRESSIBLE:
            continue
        if rule.scope is Scope.FILE:
            file_codes.add(rule.code)
        else:
            lines = source.logical.range_of(diagnostic.span.start.line)
            by_line.setdefault(lines, set()).add(rule.code)
    return by_line, file_codes


def freeze_edits(source: SourceFile, registry: Registry, diagnostics: Iterable[Diagnostic]) -> list[Edit]:
    """Return one edit per logical line to freeze, plus one for the file."""
    by_line, file_codes = _codes_to_freeze(source, registry, diagnostics)
    directives = find_directives(source, registry)
    edits = [line_edit(source, directives, *item) for item in by_line.items()]
    if file_codes:
        edits.append(file_edit(source, directives, file_codes))
    return [edit for edit in edits if edit is not None]


def add_foqa(linter: Linter, path: Path) -> int:
    """Freeze the remaining diagnostics of a file; return the lines edited."""
    report = linter.check_path(path)
    source = report.source
    if source is None or source.syntax_error is not None:
        return 0
    edits = freeze_edits(source, linter.registry, report.diagnostics)
    if edits:
        write_source(source, apply_edits(source.text, edits))
    return len(edits)


def render_added(count: int) -> str | None:
    """Return ``Added {n} foqa directive{s}.``, or ``None`` if nothing was added."""
    if not count:
        return None
    return ADDED.format(count=count, plural=plural(count))
