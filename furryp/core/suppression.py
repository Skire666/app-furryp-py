"""``foqa`` directives: detection with tokenize, filter and usage (SPEC §6).

``# foqa[:CODES]`` applies to the logical line of its comment. ``# furryp:
foqa[:CODES]``, alone on its line, applies to the whole file. Only ``COMMENT``
tokens are read: a ``# foqa`` inside a string does not count. The filter
records which code of which directive suppressed a diagnostic, for FUR001.

A comment is read as ruff 0.17.3 reads its own directive: only the first keyword
of each form counts, even if what follows it is invalid. Then a warning says why,
and the directive suppresses nothing.
"""

import re
import tokenize
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from furryp.core.diagnostic import Diagnostic, Span, line_span
from furryp.core.registry import Registry
from furryp.core.source import SourceFile


class DirectiveKind(StrEnum):
    """Reach of a directive: its logical line, or the whole file."""

    LINE = "line"
    FILE = "file"


LINE_KEYWORD = re.compile(r"#\s*(?i:foqa)")
FILE_KEYWORD = re.compile(r"#\s*furryp\s*:\s*(?i:foqa)")
COLON = re.compile(r"\s*:")
CODE_WORD = re.compile(r"[A-Z]+[0-9]+")
NAME_WORD = re.compile(r"[a-z][a-z0-9-]*")
LIST_SEPARATOR = ","
COMMENT_START = "#"
BLANKET = None
EXPECTED_COLON = (
    "expected `:` followed by a comma-separated list of codes"
    " (e.g., `# foqa:FUR101,FUR403`)."
)
EXPECTED_LIST = (
    "expected a comma-separated list of codes (e.g., `# foqa:FUR101,FUR403`)."
)
EXPECTED_CODE = (
    "expected code to consist of uppercase letters followed by digits only"
    " (e.g. `FUR101`)"
)
MISSING_CODE = "expected rule code between commas"
JOINED_CODES = "expected comma or space delimiter between codes"
INVALID_WARNINGS = {
    DirectiveKind.LINE: "Invalid `# foqa` directive on {location}: {reason}",
    DirectiveKind.FILE: "Invalid `# furryp: foqa` directive at {location}: {reason}",
}
LIST_WARNING = "Missing or joined rule code(s) at {location}: {reason}"
MISPLACED_WARNING = (
    "Unexpected `# furryp: foqa` directive at {location}. File-level suppression"
    " comments must appear on their own line. For line-level suppression, omit the"
    " `furryp:` prefix."
)
DIRECTIVE_PREFIXES = {
    DirectiveKind.LINE: "# foqa",
    DirectiveKind.FILE: "# furryp: foqa",
}
COMPACT_SEPARATOR = ","


@dataclass(frozen=True, slots=True)
class Directive:
    """A ``foqa`` directive; no ``identifiers`` means a blanket directive.

    ``first_line`` and ``last_line`` bound the logical line of a line
    directive; ``span`` covers the directive inside its comment.
    """

    kind: DirectiveKind
    identifiers: tuple[str, ...]
    span: Span
    first_line: int
    last_line: int

    def covers(self, line: int) -> bool:
        """Whether a diagnostic starting on ``line`` is within reach."""
        if self.kind is DirectiveKind.FILE:
            return True
        return self.first_line <= line <= self.last_line


def format_directive(kind: DirectiveKind, identifiers: Iterable[str]) -> str:
    """Return a directive in the compact format: ``# foqa:FUR101,FUR403`` (A22).

    The file form is ``# furryp: foqa:FUR102``; the identifiers are written in
    the given order.
    """
    return f"{DIRECTIVE_PREFIXES[kind]}:{COMPACT_SEPARATOR.join(identifiers)}"


@dataclass(frozen=True, slots=True)
class _RuleList:
    """What follows a keyword: the identifiers and where they end, what makes the
    directive invalid, and what only deserves a warning."""

    identifiers: tuple[str, ...] = ()
    end: int = 0
    invalid: str | None = None
    problems: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DirectiveScan:
    """The directives of a file, in order, and the warnings about them: those of
    the file directives first, as ruff prints them."""

    directives: tuple[Directive, ...]
    warnings: tuple[str, ...]


def _word_at(text: str, position: int, registry: Registry) -> str | None:
    """Return the code, known or not, or the known rule name at ``position``."""
    match = CODE_WORD.match(text, position)
    if match is not None:
        return match.group()
    match = NAME_WORD.match(text, position)
    if match is not None and registry.find(match.group()) is not None:
        return match.group()
    return None


def _ends_word(text: str, position: int) -> bool:
    """Whether a word can stop at ``position``: at the end, a blank or a ``#``."""
    following = text[position : position + 1]
    return not following or following.isspace() or following == COMMENT_START


def _parse_rule_list(
    text: str, position: int, registry: Registry
) -> _RuleList:  # foqa:FUR203
    """Read the identifiers after the colon, separated by commas or blanks.

    The list stops at the first word that is not an identifier: the rest of the
    comment is free text. A comma without a code before it and two joined codes
    only deserve a warning.
    """
    identifiers: list[str] = []
    problems: list[str] = []
    end = position
    while position < len(text):
        if text[position].isspace():
            position += 1
        elif text[position] == LIST_SEPARATOR:
            problems.append(MISSING_CODE)
            position += 1
        else:
            word = _word_at(text, position, registry)
            if word is None:
                break
            identifiers.append(word)
            end = position = position + len(word)
            if text.startswith(LIST_SEPARATOR, position):
                position += 1
            elif CODE_WORD.match(text, position):
                problems.append(JOINED_CODES)
            elif not _ends_word(text, position):
                return _RuleList(invalid=EXPECTED_CODE)
    if not identifiers:
        return _RuleList(invalid=EXPECTED_LIST)
    return _RuleList(tuple(identifiers), end, None, tuple(problems))


def _parse_after_keyword(text: str, position: int, registry: Registry) -> _RuleList:
    """Read what follows a keyword: a list after a colon, or a blanket directive
    when a blank, a ``#`` or nothing follows, whatever comes next."""
    colon = COLON.match(text, position)
    if colon is not None:
        return _parse_rule_list(text, colon.end(), registry)
    if _ends_word(text, position):
        return _RuleList(end=position)
    return _RuleList(invalid=EXPECTED_COLON)


class _Scanner:
    """Reads the directives of the comments of a file, and their warnings."""

    def __init__(self, source: SourceFile, registry: Registry) -> None:
        self._source = source
        self._registry = registry
        self._directives: list[Directive] = []
        self._warnings: dict[DirectiveKind, list[str]] = {
            DirectiveKind.FILE: [],
            DirectiveKind.LINE: [],
        }

    def scan(self) -> DirectiveScan:
        """Read every comment token (none without tokens)."""
        for token in self._source.tokens or ():
            if token.type == tokenize.COMMENT:
                self._read_file_form(token)
                self._read_line_form(token)
        warnings = (
            *self._warnings[DirectiveKind.FILE],
            *self._warnings[DirectiveKind.LINE],
        )
        return DirectiveScan(tuple(self._directives), warnings)

    def _read_file_form(self, token: tokenize.TokenInfo) -> None:
        """Read ``# furryp: foqa``, which only counts alone on its line."""
        match = FILE_KEYWORD.search(token.string)
        if match is None:
            return
        line, column = token.start
        rules = self._parse(DirectiveKind.FILE, match, token)
        if rules is None:
            return
        if self._source.lines[line - 1][:column].strip():
            warning = MISPLACED_WARNING.format(location=self._location(line))
            self._warnings[DirectiveKind.FILE].append(warning)
            return
        self._add(DirectiveKind.FILE, match, token, rules, (line, line))

    def _read_line_form(self, token: tokenize.TokenInfo) -> None:
        """Read ``# foqa``, which covers the logical line of its comment."""
        match = LINE_KEYWORD.search(token.string)
        if match is None:
            return
        rules = self._parse(DirectiveKind.LINE, match, token)
        if rules is not None:
            lines = self._source.logical.range_of(token.start[0])
            self._add(DirectiveKind.LINE, match, token, rules, lines)

    def _location(self, line: int) -> str:
        """Return ``path:line``, as the warnings show it."""
        return f"{self._source.display}:{line}"

    def _parse(
        self, kind: DirectiveKind, match: re.Match[str], token: tokenize.TokenInfo
    ) -> _RuleList | None:
        """Return what follows a keyword, or ``None`` if the directive is invalid;
        the problems found go to the warnings."""
        rules = _parse_after_keyword(token.string, match.end(), self._registry)
        location = self._location(token.start[0])
        if rules.invalid is not None:
            warning = INVALID_WARNINGS[kind].format(
                location=location, reason=rules.invalid
            )
            self._warnings[kind].append(warning)
            return None
        self._warnings[kind].extend(
            LIST_WARNING.format(location=location, reason=reason)
            for reason in rules.problems
        )
        return rules

    def _add(
        self,
        kind: DirectiveKind,
        match: re.Match[str],
        token: tokenize.TokenInfo,
        rules: _RuleList,
        lines: tuple[int, int],
    ) -> None:
        """Record a directive, whose span ends with its last identifier."""
        line, column = token.start
        start, end = column + match.start() + 1, column + rules.end + 1
        span = line_span(line, start, end)
        self._directives.append(Directive(kind, rules.identifiers, span, *lines))


def scan_directives(source: SourceFile, registry: Registry) -> DirectiveScan:
    """Return the directives of ``source`` and the warnings about them."""
    return _Scanner(source, registry).scan()


def find_directives(source: SourceFile, registry: Registry) -> tuple[Directive, ...]:
    """Return the directives of ``source``, in order (none without tokens)."""
    return scan_directives(source, registry).directives


class Suppressions:
    """Filter of the diagnostics of a file by its directives.

    As ruff, the file directives come first: every one that names the rule of a
    diagnostic (or is a blanket directive) suppresses it and is recorded as used,
    and a line directive that also reaches it stays unused. Otherwise, the same
    goes for the line directives that reach it.
    """

    def __init__(self, directives: tuple[Directive, ...], registry: Registry) -> None:
        self._directives = directives
        self._registry = registry
        self._used: set[tuple[int, str | None]] = set()

    @property
    def directives(self) -> tuple[Directive, ...]:
        """The directives of the file, in order."""
        return self._directives

    @property
    def exempts_the_file(self) -> bool:
        """Whether a blanket file directive exempts the whole file."""
        return any(
            directive.kind is DirectiveKind.FILE and not directive.identifiers
            for directive in self._directives
        )

    def suppresses(self, diagnostic: Diagnostic) -> bool:
        """Whether ``diagnostic`` is suppressed; record the directives used."""
        hits = self._hits(DirectiveKind.FILE, diagnostic) or self._hits(
            DirectiveKind.LINE, diagnostic
        )
        self._used |= hits
        return bool(hits)

    def _hits(
        self, kind: DirectiveKind, diagnostic: Diagnostic
    ) -> set[tuple[int, str | None]]:
        """Return the identifiers of the directives of ``kind`` that suppress it."""
        line = diagnostic.span.start.line
        return {
            (position, identifier)
            for position, directive in enumerate(self._directives)
            if directive.kind is kind and directive.covers(line)
            for identifier in self._matching(directive, diagnostic.code)
        }

    def _matching(self, directive: Directive, code: str) -> tuple[str | None, ...]:
        """Return the identifiers of ``directive`` naming ``code``."""
        if not directive.identifiers:
            return (BLANKET,)
        return tuple(
            identifier
            for identifier in directive.identifiers
            if self._names(identifier, code)
        )

    def _names(self, identifier: str, code: str) -> bool:
        """Whether ``identifier`` (code or name) designates the rule ``code``."""
        rule = self._registry.find(identifier)
        return rule is not None and rule.code == code

    def is_used(self, position: int, identifier: str | None = BLANKET) -> bool:
        """Whether an identifier (default: the blanket) of a directive was used."""
        return (position, identifier) in self._used
