"""Rule metadata and the registry resolving codes, prefixes and names (§4.5)."""

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from furryp.core.diagnostic import Diagnostic
from furryp.core.errors import (
    RULE_OR_PREFIX,
    UnknownRuleError,
    did_you_mean,
    format_suggestion,
)
from furryp.core.names import ImportTable
from furryp.core.project import ProjectContext
from furryp.core.source import SourceFile


class Scope(StrEnum):
    """Where ``--add-foqa`` writes the directive of a rule (SPEC §6.1)."""

    LINE = "line"
    FILE = "file"


ALL_RULES_PREFIX = "FUR"
CODE_PREFIX_PATTERN = re.compile(r"FUR\d{0,3}")
CHECK_KEY = "check"


@dataclass(frozen=True, slots=True)
class RuleContext[O, M = object]:
    """What a rule sees of a file.

    The source, the typed rule options, the names imported by the module, its
    metrics and the project.

    ``M`` is the type of the metrics, which live in a higher layer: a rule that
    reads them writes ``RuleContext[Options, FileMetrics]``.
    """

    source: SourceFile
    options: O
    imports: ImportTable
    metrics: M
    project: ProjectContext


type Check = Callable[[RuleContext[Any, Any]], Iterable[Diagnostic]]


@dataclass(frozen=True, slots=True)
class Rule:
    """Description of a rule and its ``check`` function.

    ``options_type`` is a dataclass with a default per field, or ``None`` for
    a rule absent from the ``rules`` object of the configuration. A field
    declares a domain check with ``field(metadata={CHECK_KEY: function})``,
    the function returning the problem as a string, or ``None``. A
    ``textual`` rule only reads the text: it also runs on a file that does
    not tokenize or parse (SPEC FUR000).
    """

    code: str
    name: str
    category: str
    summary: str
    options_type: type | None
    fixable: bool
    scope: Scope
    check: Check
    textual: bool = False


def options_of[O](rules: Mapping[str, object], name: str, kind: type[O]) -> O:
    """Return the options of the rule ``name``, or its defaults if it is not registered.

    A rule may be missing from the fake registries of the tests.
    """
    value = rules.get(name)
    return value if isinstance(value, kind) else kind()


class Registry:
    """Lookup of rules by code, code prefix (``FUR``, ``FUR4``…) or name."""

    def __init__(self, rules: Iterable[Rule]) -> None:
        """Sort ``rules`` by code and index them by code and by name."""
        self._rules = tuple(sorted(rules, key=lambda rule: rule.code))
        self._by_key = {
            key: rule for rule in self._rules for key in (rule.code, rule.name)
        }

    @property
    def rules(self) -> tuple[Rule, ...]:
        """All the rules, sorted by code."""
        return self._rules

    def find(self, identifier: str) -> Rule | None:
        """Return the rule whose code or name is ``identifier``."""
        return self._by_key.get(identifier)

    def lookup(self, identifier: str) -> Rule:
        """Return the rule whose code or name is ``identifier``, or raise."""
        rule = self.find(identifier)
        if rule is None:
            hint = did_you_mean(identifier, self._by_key)
            raise UnknownRuleError(hint, identifier)
        return rule

    def by_name(self, name: str) -> Rule:
        """Return the rule called ``name``; a code is refused with a hint."""
        rule = self.find(name)
        if rule is not None and rule.name == name:
            return rule
        if rule is not None:
            hint = format_suggestion(rule.name)
        else:
            hint = did_you_mean(name, [known.name for known in self._rules])
        raise UnknownRuleError(hint)

    def resolve(self, selector: str) -> tuple[Rule, ...]:
        """Return the rules selected by a code, a code prefix or a name."""
        rule = self.find(selector)
        if rule is not None:
            return (rule,)
        if CODE_PREFIX_PATTERN.fullmatch(selector):
            matched = tuple(r for r in self._rules if r.code.startswith(selector))
            if matched or selector == ALL_RULES_PREFIX:
                return matched
        hint = did_you_mean(selector, self._selectors())
        raise UnknownRuleError(hint, selector, kind=RULE_OR_PREFIX)

    def _selectors(self) -> tuple[str, ...]:
        """Every valid selector: ``FUR``, family prefixes, codes and names."""
        families = {
            rule.code[:end]
            for rule in self._rules
            for end in range(len(ALL_RULES_PREFIX) + 1, len(rule.code))
        }
        return (ALL_RULES_PREFIX, *sorted(families), *self._by_key)
