"""Command-line parser: ``check`` and ``rule`` sub-commands (SPEC §4.1, §4.2)."""

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from furryp.core.errors import UsageError

PROG = "furryp"
DESCRIPTION = "A local, dependency-free Python linter inspired by ruff."
RULE_LIST_SEPARATOR = ","
RULE_LIST_OPTIONS = (
    (
        "--select",
        (
            "Comma-separated rule codes, code prefixes or names to enable, "
            "instead of the configured selection. Repeatable."
        ),
    ),
    ("--extend-select", "Comma-separated rules to add to the selection. Repeatable."),
    ("--ignore", "Comma-separated rules to remove from the selection. Repeatable."),
)
FLAG_OPTIONS = (
    ("--fix", "Apply the available fixes (all of them are safe) and write the files."),
    ("--diff", "Show the fixes as a unified diff, without writing anything."),
    ("--statistics", "Show the violation count per rule instead of the diagnostics."),
    ("--show-settings", "Print the effective configuration and exit."),
    ("--exit-zero", "Exit with 0 even if violations remain (errors still exit 2)."),
    ("--add-foqa", "Add a foqa directive on every existing violation and exit."),
)


class FurrypArgumentParser(argparse.ArgumentParser):
    """Parser raising ``UsageError`` instead of exiting on a usage error."""

    def error(self, message: str) -> NoReturn:
        """Report a usage error as ``error: {message}`` followed by the usage."""
        raise UsageError("\n".join((message, self.format_usage().rstrip())))


def _new_parser(
    commands: argparse._SubParsersAction, name: str, summary: str
) -> argparse.ArgumentParser:
    """Add the sub-command ``name`` (no colours, suggestions on typos, and no abbreviated options, like ruff)."""
    return commands.add_parser(
        name,
        help=summary,
        description=summary,
        allow_abbrev=False,
        color=False,
        suggest_on_error=True,
    )


def _add_config_option(parser: argparse.ArgumentParser) -> None:
    """Add ``--config PATH``, shared by ``check`` and ``rule``."""
    parser.add_argument(
        "--config",
        type=Path,
        metavar="PATH",
        help="Use this JSON configuration file instead of the discovered one.",
    )


def _add_check_parser(commands: argparse._SubParsersAction) -> None:
    """Add ``furryp check [PATHS]... [OPTIONS]``."""
    check = _new_parser(commands, "check", "Check Python files.")
    check.add_argument(
        "paths",
        nargs="*",
        type=Path,
        metavar="PATH",
        help="Files or directories to check (default: the current directory).",
    )
    _add_config_option(check)
    for option, summary in RULE_LIST_OPTIONS:
        check.add_argument(option, action="append", metavar="RULES", help=summary)
    for option, summary in FLAG_OPTIONS:
        check.add_argument(option, action="store_true", help=summary)
    check.add_argument(
        "--report-html",
        type=Path,
        metavar="PATH",
        help="Write the HTML audit report to PATH; nothing is printed on stdout.",
    )


def _add_rule_parser(commands: argparse._SubParsersAction) -> None:
    """Add ``furryp rule <CODE|NAME>`` and ``furryp rule --all``."""
    rule = _new_parser(commands, "rule", "Show the documentation of a rule.")
    target = rule.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "rule",
        nargs="?",
        metavar="CODE|NAME",
        help="Rule code (recommended, e.g. FUR101) or rule name.",
    )
    target.add_argument("--all", action="store_true", help="Show every rule.")
    _add_config_option(rule)


def build_parser() -> argparse.ArgumentParser:
    """Return the parser of the ``furryp`` command line."""
    parser = FurrypArgumentParser(
        prog=PROG,
        description=DESCRIPTION,
        allow_abbrev=False,
        color=False,
        suggest_on_error=True,
    )
    parser.add_argument("--version", action="store_true", help="Print the version.")
    commands = parser.add_subparsers(
        dest="command", title="commands", metavar="COMMAND"
    )
    _add_check_parser(commands)
    _add_rule_parser(commands)
    return parser


def split_rule_lists(values: Sequence[str] | None) -> tuple[str, ...]:
    """Flatten repeated comma-separated rule lists.

    An empty item or a space is kept, then refused as an unknown selector, like
    ruff: ``--select "$RULES"`` with an empty variable must not select nothing.
    """
    return tuple(
        item for value in values or () for item in value.split(RULE_LIST_SEPARATOR)
    )
