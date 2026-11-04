r"""Output of ``furryp check --diff`` (SPEC §5.3), as ruff prints it.

Each changed file gives a unified diff (``difflib``) whose two headers are its
displayed path, with the lines keeping their own line breaks; a last line
without line break is followed by ``\ No newline at end of file``, and a
blank line follows each file. The footer counts the fixes; ruff prints none
when nothing would be fixed.
"""

import difflib

from furryp.core.positions import split_lines_with_breaks
from furryp.output.terminal import plural

NO_NEWLINE = "\n\\ No newline at end of file\n"
LINE_BREAK_ENDS = ("\n", "\r")
WOULD_FIX = "Would fix {count} error{plural}."


def _terminated(line: str) -> str:
    """Return a diff line ending with a line break (marked if it had none)."""
    return line if line.endswith(LINE_BREAK_ENDS) else line + NO_NEWLINE


def render_file_diff(display: str, before: str, after: str) -> str:
    """Return the unified diff of a file, followed by a blank line."""
    lines = difflib.unified_diff(
        split_lines_with_breaks(before),
        split_lines_with_breaks(after),
        fromfile=display,
        tofile=display,
    )
    return "".join(_terminated(line) for line in lines) + "\n"


def render_diff_footer(count: int) -> str | None:
    """Return ``Would fix {n} error{s}.``, or ``None`` if nothing would be fixed."""
    if not count:
        return None
    return WOULD_FIX.format(count=count, plural=plural(count))
