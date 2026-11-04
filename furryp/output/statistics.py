"""Output of ``furryp check --statistics`` (SPEC §5.4).

One line per rule with at least one violation, by decreasing count then by
code: ``{count:>N}\\t{code}\\t{marker} {name}``, then the footer.
"""

from collections import Counter
from collections.abc import Sequence

from furryp.core.diagnostic import Diagnostic
from furryp.output.terminal import render_footer

FIXABLE_MARKER = "[*] "
NOT_FIXABLE_MARKER = "[ ] "


def _marker(code: str, fixable: set[str]) -> str:
    """Return the fix marker of a rule; there is none if no rule is fixable."""
    if not fixable:
        return ""
    return FIXABLE_MARKER if code in fixable else NOT_FIXABLE_MARKER


def render_statistics(diagnostics: Sequence[Diagnostic]) -> str:
    """Return the count of violations per rule, then the footer, as ruff 0.17.3; an empty text if there is no violation."""
    counts = Counter(diagnostic.code for diagnostic in diagnostics)
    if not counts:
        return ""
    names = {diagnostic.code: diagnostic.name for diagnostic in diagnostics}
    fixable = {d.code for d in diagnostics if d.fix is not None}
    width = len(str(max(counts.values())))
    rows = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    lines = [
        f"{count:>{width}}\t{code}\t{_marker(code, fixable)}{names[code]}"
        for code, count in rows
    ]
    return "\n".join([*lines, render_footer(diagnostics)])
