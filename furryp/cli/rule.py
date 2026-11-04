"""``furryp rule <CODE|NAME>`` and ``furryp rule --all`` (SPEC §4.6).

The configuration is discovered as for ``check``, so that the documentation shows the effective option values.
"""

import argparse
from pathlib import Path

from furryp.config.loader import load_configuration
from furryp.core.registry import Registry
from furryp.output.rule_doc import render_rules
from furryp.rules import ALL_RULES


def run_rule(args: argparse.Namespace, cwd: Path) -> None:
    """Print the documentation of the requested rule, or of every rule.

    An unknown rule raises ``UnknownRuleError`` (exit code 2).
    """
    registry = Registry(ALL_RULES)
    configuration = load_configuration(cwd, args.config, registry)
    rules = registry.rules if args.all else (registry.lookup(args.rule),)
    print(render_rules(rules, configuration.settings))
