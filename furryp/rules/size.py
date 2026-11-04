"""Size rules: FUR101 function-too-long and FUR102 file-too-long (SPEC §11)."""

from collections.abc import Iterator
from dataclasses import dataclass

from furryp.core.diagnostic import Diagnostic, line_span
from furryp.core.registry import Rule, RuleContext, Scope
from furryp.metrics.file_metrics import FileMetrics

FUNCTION_TOO_LONG_CODE = "FUR101"
FUNCTION_TOO_LONG_NAME = "function-too-long"
FUNCTION_TOO_LONG_MESSAGE = "Function `{name}` has too many lines of code ({count} > {max})"
FUNCTION_TOO_LONG_HELP = "Long functions are hard to read and test; consider splitting this one"
FILE_TOO_LONG_CODE = "FUR102"
FILE_TOO_LONG_NAME = "file-too-long"
FILE_TOO_LONG_MESSAGE = "File has too many lines ({count} > {max})"
FILE_TOO_LONG_HELP = "Long files are hard to navigate; consider splitting this one into smaller modules"


@dataclass(frozen=True, slots=True)
class FunctionTooLongOptions:
    """Options of FUR101."""

    max_lines: int = 26


def check_function_too_long(context: RuleContext[FunctionTooLongOptions, FileMetrics]) -> Iterator[Diagnostic]:
    """Report a function with more lines of code than ``max-lines``.

    Nested functions count in their parent and are also evaluated alone.
    """
    limit = context.options.max_lines
    for function in context.metrics.functions:
        if function.code_lines > limit:
            yield Diagnostic(
                FUNCTION_TOO_LONG_CODE,
                FUNCTION_TOO_LONG_NAME,
                FUNCTION_TOO_LONG_MESSAGE.format(name=function.name, count=function.code_lines, max=limit),
                context.source.path,
                function.span,
                FUNCTION_TOO_LONG_HELP,
            )


FUNCTION_TOO_LONG = Rule(
    code=FUNCTION_TOO_LONG_CODE,
    name=FUNCTION_TOO_LONG_NAME,
    category="size",
    summary="The function has too many lines of code.",
    options_type=FunctionTooLongOptions,
    fixable=False,
    scope=Scope.LINE,
    check=check_function_too_long,
)


@dataclass(frozen=True, slots=True)
class FileTooLongOptions:
    """Options of FUR102."""

    max_lines: int = 1000


def check_file_too_long(context: RuleContext[FileTooLongOptions]) -> Iterator[Diagnostic]:
    """Report a file with more physical lines than ``max-lines``."""
    source = context.source
    limit = context.options.max_lines
    count = len(source.lines)
    if count > limit:
        line = limit + 1
        span = line_span(line, 1, len(source.lines[line - 1]) + 1)
        message = FILE_TOO_LONG_MESSAGE.format(count=count, max=limit)
        yield Diagnostic(FILE_TOO_LONG_CODE, FILE_TOO_LONG_NAME, message, source.path, span, FILE_TOO_LONG_HELP)


FILE_TOO_LONG = Rule(
    code=FILE_TOO_LONG_CODE,
    name=FILE_TOO_LONG_NAME,
    category="size",
    summary="The file has too many physical lines.",
    options_type=FileTooLongOptions,
    fixable=False,
    scope=Scope.FILE,
    check=check_file_too_long,
    textual=True,
)
