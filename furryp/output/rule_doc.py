"""Documentation of a rule, shown by ``furryp rule`` (SPEC §4.6).

The written parts come from ``furryp/rules/docs/<CODE>.md``; the title, the
metadata line and the ``Options`` section, with the effective values, are
generated from the registry and the configuration.
"""

import dataclasses
import json
from collections.abc import Sequence
from importlib import resources

from furryp.config.options import Settings
from furryp.config.schema import dump_value, json_key
from furryp.core.registry import Rule

DOCS_PACKAGE = "furryp.rules"
DOCS_DIRECTORY = "docs"
DOCS_ENCODING = "utf-8"
OPTIONS_ANCHOR = "## How to fix it well"
OPTIONS_TITLE = "## Options (furryp.json → rules.{name})"
NO_OPTIONS = "## Options\n\nThis rule has no options."
OPTION_LINE = "- {key} = {value} (default: {default})"
FIX_AVAILABLE = "available"
FIX_NOT_AVAILABLE = "not available"
RULE_SEPARATOR = "\n\n---\n\n"


def read_rule_doc(code: str) -> str:
    """Return the written documentation of the rule ``code``."""
    path = resources.files(DOCS_PACKAGE).joinpath(DOCS_DIRECTORY, f"{code}.md")
    return path.read_text(encoding=DOCS_ENCODING)


def _json(value: object) -> str:
    """Return an option value as written in ``furryp.json``."""
    return json.dumps(dump_value(value), ensure_ascii=False)


def render_options(rule: Rule, options: object) -> str:
    """Return the ``Options`` section, with effective and default values."""
    if rule.options_type is None or not dataclasses.fields(rule.options_type):
        return NO_OPTIONS
    defaults = rule.options_type()
    lines = [OPTIONS_TITLE.format(name=rule.name), ""]
    for item in dataclasses.fields(rule.options_type):
        value = _json(getattr(options, item.name))
        default = _json(getattr(defaults, item.name))
        key = json_key(item.name)
        lines.append(OPTION_LINE.format(key=key, value=value, default=default))
    return "\n".join(lines)


def render_rule(rule: Rule, settings: Settings) -> str:
    """Return the Markdown documentation of ``rule``."""
    fix = FIX_AVAILABLE if rule.fixable else FIX_NOT_AVAILABLE
    metadata = f"Category: {rule.category} · Scope: {rule.scope} · Fix: {fix}"
    before, anchor, after = read_rule_doc(rule.code).partition(OPTIONS_ANCHOR)
    if not anchor:
        raise ValueError(f"{rule.code}.md has no {OPTIONS_ANCHOR!r} section")
    options = render_options(rule, settings.rules.get(rule.name))
    body = f"{before.rstrip()}\n\n{options}\n\n{anchor}{after.rstrip()}"
    return f"# {rule.name} ({rule.code})\n\n{metadata}\n\n{body}"


def render_rules(rules: Sequence[Rule], settings: Settings) -> str:
    """Return the documentation of ``rules``, separated by ``---`` lines."""
    return RULE_SEPARATOR.join(render_rule(rule, settings) for rule in rules)
