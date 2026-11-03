"""Shared helpers: fake rule registry, temporary projects, CLI runners."""

import contextlib
import errno
import io
import os
import subprocess
import sys
import tempfile
import tokenize
import unittest
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from unittest import mock

from furryp.cli.app import main
from furryp.config.loader import default_settings, parse_settings
from furryp.config.options import Settings
from furryp.core.diagnostic import Diagnostic, line_span
from furryp.core.registry import Registry, Rule, RuleContext, Scope
from furryp.core.source import SourceFile, parse_source
from furryp.lint.runner import FileReport, Linter
from furryp.rules import ALL_RULES

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = "pyproject.toml"
CONFIG = "furryp.json"
# A statement flagged by FUR403 (demeter-chain), a rule of scope ``line``.
FLAGGED = "x = a.b.c.d.e"
FORBIDDEN_COMBINATIONS = {
    "--add-foqa": [
        "--fix",
        "--diff",
        "--statistics",
        "--show-settings",
        "--report-html",
    ],
    "--report-html": ["--fix", "--diff", "--statistics", "--show-settings"],
    "--statistics": ["--fix", "--diff"],
    "--show-settings": ["--fix", "--diff", "--statistics"],
}


@dataclass(frozen=True, slots=True)
class LengthOptions:
    """Fake options: integer, boolean and list fields."""

    max_lines: int = 25
    count_blank_lines: bool = True
    exclude_methods: tuple[str, ...] = ("__init__", "__new__")


@dataclass(frozen=True, slots=True)
class NestedNames:
    """Fake nested options object (merged key by key)."""

    first: str = "one"
    second: str = "two"


@dataclass(frozen=True, slots=True)
class MetricOptions:
    """Fake options: literal, integer, free-key object and nested object."""

    metric: Literal["volume", "difficulty", "effort", "bugs"] = "volume"
    max: int = 1000
    aliases: dict[str, str] = field(default_factory=lambda: {"vol": "volume"})
    names: NestedNames = field(default_factory=NestedNames)


@dataclass(frozen=True, slots=True)
class NoOptions:
    """Fake rule without options."""


def no_check(context: RuleContext[Any]) -> Iterator[Diagnostic]:
    """Fake check reporting nothing."""
    yield from ()


FAKE_RULES = (
    Rule(
        "FUR101",
        "function-too-long",
        "size",
        "Long function.",
        LengthOptions,
        False,
        Scope.LINE,
        no_check,
    ),
    Rule(
        "FUR201",
        "halstead-file",
        "halstead",
        "Halstead.",
        MetricOptions,
        False,
        Scope.FILE,
        no_check,
    ),
    Rule(
        "FUR001",
        "unused-foqa",
        "suppressions",
        "Unused foqa.",
        NoOptions,
        True,
        Scope.LINE,
        no_check,
    ),
)


def fake_registry() -> Registry:
    """Return a registry of three fake rules with typed options."""
    return Registry(FAKE_RULES)


def write_files(root: Path, files: dict[str, str | bytes]) -> None:
    """Create ``files`` (relative path → text or bytes) below ``root``."""
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        data = content if isinstance(content, bytes) else content.encode("utf-8")
        path.write_bytes(data)


def with_value(option: str) -> list[str]:
    """Return the arguments of ``option`` (``--report-html`` takes a path)."""
    return [option, "out.html"] if option == "--report-html" else [option]


class TempDirTestCase(unittest.TestCase):
    """Test case with a fresh, resolved temporary directory in ``self.root``."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()


def run_main(args: Sequence[str], cwd: Path) -> tuple[int, str, str]:
    """Run ``main(args)`` in this process from ``cwd``: (code, stdout, stderr)."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        contextlib.chdir(cwd),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        code = main(list(args))
    return code, stdout.getvalue(), stderr.getvalue()


def run_furryp(
    args: Sequence[str], cwd: Path, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run ``python -m furryp`` in a subprocess from ``cwd``."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, "-m", "furryp", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )


def run_furryp_raw(
    args: Sequence[str], cwd: Path
) -> subprocess.CompletedProcess[bytes]:
    """Run ``python -m furryp`` and keep the raw bytes of its output.

    Nothing is decoded: it is the only way to see the ``\\r\\n`` written.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "furryp", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        check=False,
    )


def real_registry() -> Registry:
    """Return the registry of the shipped rules."""
    return Registry(ALL_RULES)


def make_settings(data: dict[str, object] | None = None) -> Settings:
    """Return the default settings updated with a ``furryp.json``-like dict."""
    registry = real_registry()
    return parse_settings(data or {}, default_settings(registry), registry)


def lint_text(
    text: str, settings: Settings | None = None, name: str = "example.py"
) -> FileReport:
    """Check ``text`` as a file ``REPO_ROOT / name`` with the shipped rules."""
    path = REPO_ROOT / name
    source = parse_source(path, name, text, "utf-8")
    linter = Linter(real_registry(), settings or make_settings(), REPO_ROOT, REPO_ROOT)
    return linter.check_source(source)


def name_rule(code: str, name: str, word: str) -> Rule:
    """Return a fake rule of scope ``line`` flagging every name ``word``."""

    def check(context: RuleContext[Any]) -> Iterator[Diagnostic]:
        source = context.source
        for token in source.tokens or ():
            if token.type == tokenize.NAME and token.string == word:
                (line, column), (_, end) = token.start, token.end
                span = line_span(line, column + 1, end + 1)
                yield Diagnostic(code, name, f"`{word}`", source.path, span, "Rename")

    return Rule(code, name, "test", "Fake.", None, False, Scope.LINE, check)


FLAG_BAD = name_rule("FUR901", "flag-bad", "bad")
FLAG_WORSE = name_rule("FUR902", "flag-worse", "worse")


def linter_with(
    rules: Sequence[Rule] = (),
    data: dict[str, object] | None = None,
    root: Path = REPO_ROOT,
) -> Linter:
    """Return a linter of the shipped rules plus ``rules``, from ``root``."""
    registry = Registry([*ALL_RULES, *rules])
    settings = parse_settings(data or {}, default_settings(registry), registry)
    return Linter(registry, settings, root, root)


def text_source(text: str, name: str = "example.py") -> SourceFile:
    """Return ``text`` as the source of a file ``REPO_ROOT / name``."""
    return parse_source(REPO_ROOT / name, name, text, "utf-8")


def codes_at(report: FileReport) -> list[str]:
    """Return the diagnostics of ``report`` as sorted ``LINE:COLUMN CODE``."""
    return sorted(
        f"{d.span.start.line}:{d.span.start.column} {d.code}"
        for d in report.diagnostics
    )


@contextlib.contextmanager
def unreadable_directory(directory: Path) -> Iterator[None]:
    """Make ``directory`` impossible to list, as without read permission.

    ``os.walk`` (used by ``Path.walk``) calls ``os.scandir``: refusing it is
    portable, whereas real permissions differ between Windows and POSIX (and
    root ignores them).
    """
    real_scandir = os.scandir

    def scandir(path: Any = ".") -> Any:
        if Path(path) == directory:
            raise PermissionError(errno.EACCES, "Permission denied", str(path))
        return real_scandir(path)

    with mock.patch("os.scandir", side_effect=scandir):
        yield
