"""Entry point of the ``furryp`` command: dispatch and exit codes (SPEC §4)."""

import argparse
import io
import sys
from collections.abc import Callable, Sequence
from datetime import datetime
from enum import IntEnum
from functools import partial
from pathlib import Path

from furryp import __version__
from furryp.cli.parser import PROG, build_parser, split_rule_lists
from furryp.cli.rule import run_rule
from furryp.config.loader import Configuration, load_configuration
from furryp.config.options import file_filter
from furryp.config.selection import CliSelection
from furryp.core.discovery import DiscoveryResult, discover_files
from furryp.core.errors import FileFailure, FurrypError, UsageError
from furryp.core.paths import display_path
from furryp.core.registry import Registry
from furryp.fix.diff import render_diff_footer, render_file_diff
from furryp.fix.engine import FixResult, fix_path, write_fixes
from furryp.fix.foqa import add_foqa, render_added
from furryp.lint.runner import Linter
from furryp.output.settings import render_settings
from furryp.output.statistics import render_statistics
from furryp.output.terminal import collect_entries, render_check
from furryp.report.files import summarize_path
from furryp.report.model import Clock, Timing, build_report
from furryp.report.render import render_report, write_report
from furryp.rules import ALL_RULES


class ExitCode(IntEnum):
    """Exit codes of furryp (SPEC §4.4)."""

    SUCCESS = 0
    VIOLATIONS = 1
    ERROR = 2


FORBIDDEN_COMBINATIONS = (
    ("add_foqa", ("fix", "diff", "statistics", "show_settings", "report_html")),
    ("report_html", ("fix", "diff", "statistics", "show_settings")),
    ("statistics", ("fix", "diff")),
    ("show_settings", ("fix", "diff", "statistics")),
)
DEFAULT_PATHS = (Path("."),)
STREAM_ENCODING = "utf-8"
STREAM_ERRORS = "replace"
STREAM_NEWLINE = "\n"
NO_FILES_WARNING = "warning: No Python files found under the given path(s)"
ENCOUNTERED_ERROR = "warning: Encountered error: "
REVERTED = "Fix introduced a syntax error in {path}; reverting"


def main(argv: Sequence[str] | None = None) -> int:
    """Run furryp with ``argv`` (default: ``sys.argv[1:]``); return the exit code."""
    configure_streams()
    parser = build_parser()
    try:
        return _dispatch(parser, parser.parse_args(argv))
    except FurrypError as error:
        _print_error(str(error))
    except Exception as error:  # noqa: BLE001
        _print_error(f"internal error: {type(error).__name__}: {error}")
    return ExitCode.ERROR


def configure_streams() -> None:
    """Write UTF-8 with ``\\n`` line ends on stdout and stderr (SPEC §5.7).

    Without ``newline``, Windows would turn every ``\\n`` into ``\\r\\n``: the
    output is the same bytes on every platform, as ruff's.
    """
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(
                encoding=STREAM_ENCODING, errors=STREAM_ERRORS, newline=STREAM_NEWLINE
            )


def _print_error(message: str) -> None:
    """Print ``error: {message}`` on stderr."""
    print(f"error: {message}", file=sys.stderr)


def _print_warning(message: str) -> None:
    """Print ``warning: {message}`` on stderr."""
    print(f"warning: {message}", file=sys.stderr)


def _dispatch(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    """Run the requested command."""
    if args.version:
        print(f"{PROG} {__version__}")
        return ExitCode.SUCCESS
    if args.command == "check":
        return run_check(args, Path.cwd().resolve())
    if args.command == "rule":
        run_rule(args, Path.cwd().resolve())
        return ExitCode.SUCCESS
    parser.error("a command is required")


def _flag(destination: str) -> str:
    """Return the command-line flag of an argparse destination."""
    return "--" + destination.replace("_", "-")


def check_combinations(args: argparse.Namespace) -> None:
    """Refuse the forbidden option combinations (SPEC §4.3)."""
    for option, conflicts in FORBIDDEN_COMBINATIONS:
        if not getattr(args, option):
            continue
        for conflict in conflicts:
            if getattr(args, conflict):
                raise UsageError(
                    f"{_flag(option)} cannot be used with {_flag(conflict)}"
                )


def _cli_selection(args: argparse.Namespace) -> CliSelection:
    """Return the rule selection given on the command line."""
    select = None if args.select is None else split_rule_lists(args.select)
    extend_select = split_rule_lists(args.extend_select)
    return CliSelection(select, extend_select, split_rule_lists(args.ignore))


def compute_exit_code(violations: int, errors: int, exit_zero: bool) -> ExitCode:
    """Return the exit code: 2 wins over 1, ``--exit-zero`` never hides 2."""
    if errors:
        return ExitCode.ERROR
    if violations and not exit_zero:
        return ExitCode.VIOLATIONS
    return ExitCode.SUCCESS


def for_each_file[T](
    paths: Sequence[Path], cwd: Path, action: Callable[[Path], T]
) -> tuple[list[T], list[FileFailure]]:
    """Run ``action`` on each path; an internal error is reported, then skipped.

    Return the results and the files that failed (SPEC §4.4).
    """
    results: list[T] = []
    failures: list[FileFailure] = []
    for path in paths:
        try:
            results.append(action(path))
        except Exception as error:  # noqa: BLE001
            reason = f"{type(error).__name__}: {error}"
            _print_error(f"Failed to check {display_path(path, cwd)}: {reason}")
            failures.append(FileFailure(path, reason))
    return results, failures


def warn_discovery(discovery: DiscoveryResult, cwd: Path) -> None:
    """Print the discovery warnings on stderr, as ruff does.

    A directory that cannot be listed is a warning, not a violation (ruff
    0.17.3: ``warning: Encountered error: …``, exit code 0); the warning
    "No Python files found" only comes when nothing at all was found.
    """
    for error in discovery.unreadable:
        location = display_path(error.path, cwd)
        print(f"{ENCOUNTERED_ERROR}{location}: {error.reason}", file=sys.stderr)
    if not (discovery.files or discovery.missing or discovery.unreadable):
        print(NO_FILES_WARNING, file=sys.stderr)


def lint_files(
    linter: Linter, paths: Sequence[Path], cwd: Path, args: argparse.Namespace
) -> int:
    """Check the files and print the diagnostics or the statistics."""
    reports, failures = for_each_file(paths, cwd, linter.check_path)
    entries = collect_entries(reports, cwd)
    diagnostics = [entry.diagnostic for entry in entries]
    text = render_statistics(diagnostics) if args.statistics else render_check(entries)
    if text:
        print(text)
    return compute_exit_code(len(entries), len(failures), args.exit_zero)


def _fix_path(linter: Linter, write: bool, path: Path) -> FixResult:
    """Fix a file in memory, then write it if ``write`` and it changed."""
    result = fix_path(linter, path)
    if write:
        write_fixes(result)
    return result


def _fixed_files(
    linter: Linter, paths: Sequence[Path], cwd: Path, write: bool
) -> tuple[list[FixResult], int]:
    """Fix the files (and write them if ``write``); report the reverted ones.

    Return the results and the number of files that failed.
    """
    results, failures = for_each_file(paths, cwd, partial(_fix_path, linter, write))
    for result in results:
        if result.reverted:
            _print_error(REVERTED.format(path=display_path(result.report.path, cwd)))
    return results, len(failures)


def fix_files(
    linter: Linter, paths: Sequence[Path], cwd: Path, args: argparse.Namespace
) -> int:
    """``--fix``: write the fixes, then print the remaining diagnostics."""
    results, errors = _fixed_files(linter, paths, cwd, write=True)
    entries = collect_entries([result.report for result in results], cwd)
    print(render_check(entries, sum(result.fixed for result in results)))
    return compute_exit_code(len(entries), errors, args.exit_zero)


def diff_files(
    linter: Linter, paths: Sequence[Path], cwd: Path, args: argparse.Namespace
) -> int:
    """``--diff``: print the diff of the fixes, write nothing (exit 1 if any)."""
    results, errors = _fixed_files(linter, paths, cwd, write=False)
    changed = sorted(
        (result for result in results if result.changed),
        key=lambda result: display_path(result.report.path, cwd),
    )
    for result in changed:
        display = display_path(result.report.path, cwd)
        print(render_file_diff(display, result.text_read, result.text), end="")
    footer = render_diff_footer(sum(result.fixed for result in changed))
    if footer is not None:
        print(footer)
    return compute_exit_code(len(changed), errors, args.exit_zero)


def add_foqa_files(
    linter: Linter, paths: Sequence[Path], cwd: Path, args: argparse.Namespace
) -> int:
    """``--add-foqa``: freeze the remaining diagnostics; report on stderr (ruff)."""
    counts, failures = for_each_file(paths, cwd, partial(add_foqa, linter))
    message = render_added(sum(counts))
    if message is not None:
        print(message, file=sys.stderr)
    return compute_exit_code(0, len(failures), args.exit_zero)


def local_now() -> datetime:
    """Return the local date and time, with its offset."""
    return datetime.now().astimezone()


def report_files(
    configuration: Configuration,
    clock: Clock,
    linter: Linter,
    paths: Sequence[Path],
    cwd: Path,
    args: argparse.Namespace,
) -> int:
    """``--report-html``: write the report; nothing on stdout (SPEC §5.6).

    The exit code is the one of ``check``: the whole selection counts, the files
    left out of the aggregates included.
    """
    started = clock()
    action = partial(summarize_path, linter, cwd)
    results, failures = for_each_file(paths, cwd, action)
    timing = Timing(started, clock())
    registry = linter.registry
    model = build_report(configuration, registry, results, failures, cwd, timing)
    write_report(args.report_html, render_report(model))
    return compute_exit_code(model.total_violations, len(failures), args.exit_zero)


type Mode = Callable[[Linter, Sequence[Path], Path, argparse.Namespace], int]


def _mode(args: argparse.Namespace, configuration: Configuration) -> Mode:
    """Return the function of the requested mode (``--fix --diff`` is ``--diff``)."""
    if args.report_html is not None:
        return partial(report_files, configuration, local_now)
    if args.add_foqa:
        return add_foqa_files
    if args.diff:
        return diff_files
    if args.fix:
        return fix_files
    return lint_files


def run_check(args: argparse.Namespace, cwd: Path) -> int:
    """Run ``furryp check`` from ``cwd`` and return the exit code."""
    check_combinations(args)
    registry = Registry(ALL_RULES)
    configuration = load_configuration(cwd, args.config, registry, _cli_selection(args))
    if args.show_settings:
        print(render_settings(configuration))
        return ExitCode.SUCCESS
    root, settings = configuration.project_root, configuration.settings
    paths = args.paths or DEFAULT_PATHS
    discovery = discover_files(paths, cwd, root, file_filter(settings))
    warn_discovery(discovery, cwd)
    linter = Linter(registry, settings, root, cwd, _print_warning)
    mode = _mode(args, configuration)
    return mode(linter, discovery.files + discovery.missing, cwd, args)
