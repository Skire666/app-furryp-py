"""FUR000 invalid-syntax: unreadable, undecodable or unparsable files.

Always selected, never suppressed. The diagnostics of an unreadable or
undecodable file are built by ``lint.runner``, which has no source to check.
"""

from collections.abc import Iterator
from pathlib import Path

from furryp.core.diagnostic import FILE_START, Diagnostic
from furryp.core.registry import Rule, RuleContext, Scope

CODE = "FUR000"
NAME = "invalid-syntax"
SYNTAX_MESSAGE = "SyntaxError: {message}"
DECODE_MESSAGE = "Failed to decode file: {message}"
READ_MESSAGE = "Failed to read file: {message}"
SYNTAX_HELP = "Fix the syntax error; other checks are skipped for this file"
DECODE_HELP = (
    "Save the file as UTF-8, or declare its encoding with a `# -*- coding: … -*-` line"
)
READ_HELP = "Check that the path exists and is readable"


def check_invalid_syntax(context: RuleContext[None]) -> Iterator[Diagnostic]:
    """Report the tokenize or parse error of the file, if any."""
    source = context.source
    problem = source.syntax_error
    if problem is not None:
        message = SYNTAX_MESSAGE.format(message=problem.message)
        yield Diagnostic(CODE, NAME, message, source.path, problem.span, SYNTAX_HELP)


INVALID_SYNTAX = Rule(
    code=CODE,
    name=NAME,
    category="errors",
    summary="The file cannot be read, decoded, tokenized or parsed.",
    options_type=None,
    fixable=False,
    scope=Scope.FILE,
    check=check_invalid_syntax,
    textual=True,
)


def read_failure(path: Path, reason: str) -> Diagnostic:
    """Return the diagnostic of a path that cannot be read, at 1:1."""
    message = READ_MESSAGE.format(message=reason)
    return Diagnostic(CODE, NAME, message, path, FILE_START, READ_HELP)


def decode_failure(path: Path, reason: str) -> Diagnostic:
    """Return the diagnostic of a file that cannot be decoded, at 1:1."""
    message = DECODE_MESSAGE.format(message=reason)
    return Diagnostic(CODE, NAME, message, path, FILE_START, DECODE_HELP)
