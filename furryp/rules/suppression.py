"""FUR001 unused-foqa: directives that suppress nothing (SPEC §6, FUR001).

The rule is declared like the others (code, name, documentation, selection)
but ``lint.runner`` evaluates it after the ``foqa`` filter, the only step that
knows the usage of each directive: its ``check`` reports nothing.

As ruff's RUF100 (ruff has priority over the spec): one diagnostic per
directive, listing its identifiers by reason, in this order: ``unused``,
``non-enabled`` (rule not selected for the file) and ``duplicated`` (rule
already named, by its code or its name). An identifier that names no rule is
ignored, as ruff ignores the codes it does not know, unless it is repeated. A
blanket file directive exempts its whole file from the rule, as from RUF100.

The fix, as ruff's, rewrites a reported directive with the identifiers that
served, in the compact format. An emptied directive is removed with the blanks
around it, another comment of the line is kept, and a line left empty is
deleted.
"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum

from furryp.core.diagnostic import Diagnostic, Edit, Fix
from furryp.core.registry import Registry, Rule, RuleContext, Scope
from furryp.core.source import SourceFile
from furryp.core.suppression import Directive, Suppressions, format_directive


class Reason(StrEnum):
    """Why an identifier of a directive is reported, in the order of ruff."""

    UNUSED = "unused"
    NON_ENABLED = "non-enabled"
    DUPLICATED = "duplicated"


CODE = "FUR001"
NAME = "unused-foqa"
UNUSED_MESSAGE = "Unused `foqa` directive ({reasons})"
UNUSED_BLANKET_MESSAGE = "Unused blanket `foqa` directive"
UNUSED_HELP = "Remove unused `foqa` directive"
REASON_SEPARATOR = "; "
CODE_SEPARATOR = ", "


@dataclass(frozen=True, slots=True)
class UnusedFoqaOptions:
    """FUR001 has no options."""


def check_unused_foqa(context: RuleContext[UnusedFoqaOptions]) -> Iterator[Diagnostic]:
    """Report nothing: ``lint.runner`` evaluates FUR001 after the filter."""
    yield from ()


UNUSED_FOQA = Rule(
    code=CODE,
    name=NAME,
    category="suppressions",
    summary="A foqa directive is unused or repeats a rule.",
    options_type=UnusedFoqaOptions,
    fixable=True,
    scope=Scope.LINE,
    check=check_unused_foqa,
)


def unused_foqa(
    suppressions: Suppressions, registry: Registry, selected: frozenset[str], source: SourceFile
) -> list[Diagnostic]:
    """Return the FUR001 diagnostics of the directives of a file.

    ``selected`` holds the codes of the rules selected for the file.
    """
    if suppressions.exempts_the_file:
        return []
    return DirectiveAudit(suppressions, registry, selected).diagnostics(source)


def removal(source: SourceFile, line: int, start: int, end: int) -> Edit:
    """Return the edit removing ``text[start:end]`` from ``line``, as ruff does.

    When another comment follows, the blanks after the removed text go with
    it; otherwise the blanks before it and any text after it go, and a line
    left empty is deleted.
    """
    line_start, next_start = source.line_bounds(line)
    line_end = line_start + len(source.lines[line - 1])
    before, after = source.text[line_start:start], source.text[end:line_end]
    if after.lstrip().startswith("#"):
        return Edit(start, end + len(after) - len(after.lstrip()), "")
    if before.strip():
        return Edit(line_start + len(before.rstrip()), line_end, "")
    return Edit(line_start, next_start, "")


def directive_fix(source: SourceFile, directive: Directive, kept: Sequence[str]) -> Fix:
    """Rewrite ``directive`` with the ``kept`` identifiers, or remove it."""
    start = source.index.index(directive.span.start)
    end = source.index.index(directive.span.end)
    if kept:
        return Fix((Edit(start, end, format_directive(directive.kind, kept)),))
    return Fix((removal(source, directive.span.start.line, start, end),))


class DirectiveAudit:
    """Audit of the directives of a file, after the ``foqa`` filter."""

    def __init__(self, suppressions: Suppressions, registry: Registry, selected: frozenset[str]) -> None:
        """Keep the filter of the file, the registry and the selected codes."""
        self._suppressions = suppressions
        self._registry = registry
        self._selected = selected

    def diagnostics(self, source: SourceFile) -> list[Diagnostic]:
        """Return one diagnostic per directive that does not fully serve."""
        diagnostics = []
        for position, directive in enumerate(self._suppressions.directives):
            problem = self._problem(position, directive)
            if problem is not None:
                message, kept = problem
                fix = directive_fix(source, directive, kept)
                diagnostics.append(Diagnostic(CODE, NAME, message, source.path, directive.span, UNUSED_HELP, fix))
        return diagnostics

    def _problem(self, position: int, directive: Directive) -> tuple[str, list[str]] | None:
        """Return the message of a directive and its identifiers that served, or ``None`` if it fully serves."""
        if not directive.identifiers:
            if self._suppressions.is_used(position):
                return None
            return UNUSED_BLANKET_MESSAGE, []
        groups, kept = self._classify(position, directive)
        if not groups:
            return None
        reasons = REASON_SEPARATOR.join(
            f"{reason}: " + CODE_SEPARATOR.join(f"`{item}`" for item in identifiers)
            for reason, identifiers in groups.items()
        )
        return UNUSED_MESSAGE.format(reasons=reasons), kept

    def _classify(self, position: int, directive: Directive) -> tuple[dict[Reason, list[str]], list[str]]:
        """Return the reported identifiers of a directive and those that served.

        The reported ones are grouped by reason; those that served stay in order.
        """
        groups: dict[Reason, list[str]] = {}
        kept: list[str] = []
        seen: set[str] = set()
        for identifier in directive.identifiers:
            rule = self._registry.find(identifier)
            key = identifier if rule is None else rule.code
            reason = self._reason(rule, key in seen, position, identifier)
            if reason is not None:
                groups.setdefault(reason, []).append(identifier)
            elif rule is not None:
                kept.append(identifier)
            seen.add(key)
        ordered = {reason: groups[reason] for reason in Reason if reason in groups}
        return ordered, kept

    def _reason(self, rule: Rule | None, duplicated: bool, position: int, identifier: str) -> Reason | None:
        """Return why an identifier is reported, or ``None`` if it served or names no rule."""
        if duplicated:
            return Reason.DUPLICATED
        if rule is None:
            return None
        if rule.code not in self._selected:
            return Reason.NON_ENABLED
        if self._suppressions.is_used(position, identifier):
            return None
        return Reason.UNUSED
