"""Metric rules: FUR201 halstead-file, FUR202 halstead-function and FUR203 cognitive-complexity (SPEC §11).

The measures come from ``FileMetrics``; these rules compare them to their
thresholds. Their help is one fixed sentence: naming what weighs the most would
point at a detail rather than at the whole function (§11.0).
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from furryp.core.diagnostic import FILE_START, Diagnostic
from furryp.core.registry import Rule, RuleContext, Scope
from furryp.metrics.file_metrics import FileMetrics
from furryp.metrics.halstead import metric_value

HALSTEAD_METRIC = Literal["volume", "difficulty", "effort", "bugs"]
HALSTEAD_FILE_CODE = "FUR201"
HALSTEAD_FILE_NAME = "halstead-file"
HALSTEAD_FILE_MESSAGE = (
    "Halstead {metric} of the file is too high ({value:.1f} > {max})"
)
HALSTEAD_FILE_HELP = "This file does a lot; consider splitting it or simplifying it"
HALSTEAD_FUNCTION_CODE = "FUR202"
HALSTEAD_FUNCTION_NAME = "halstead-function"
HALSTEAD_FUNCTION_MESSAGE = (
    "Halstead {metric} of function `{name}` is too high ({value:.1f} > {max})"
)
HALSTEAD_FUNCTION_HELP = (
    "This function does a lot; consider splitting it or simplifying it"
)
COGNITIVE_CODE = "FUR203"
COGNITIVE_NAME = "cognitive-complexity"
COGNITIVE_MESSAGE = (
    "Cognitive complexity of function `{name}` is too high ({value} > {max})"
)
COGNITIVE_HELP = (
    "Branches and nesting make this function hard to follow; "
    "consider simplifying its control flow"
)


@dataclass(frozen=True, slots=True)
class HalsteadFileOptions:
    """Options of FUR201."""

    metric: HALSTEAD_METRIC = "volume"
    max: int = 15000


@dataclass(frozen=True, slots=True)
class HalsteadFunctionOptions:
    """Options of FUR202."""

    metric: HALSTEAD_METRIC = "volume"
    max: int = 1200


@dataclass(frozen=True, slots=True)
class CognitiveComplexityOptions:
    """Options of FUR203."""

    max: int = 16


def check_halstead_file(
    context: RuleContext[HalsteadFileOptions, FileMetrics],
) -> Iterator[Diagnostic]:
    """Report a file whose Halstead metric is above ``max``."""
    options, metrics = context.options, context.metrics
    value = metric_value(metrics.halstead, options.metric)
    if value > options.max:
        yield Diagnostic(
            HALSTEAD_FILE_CODE,
            HALSTEAD_FILE_NAME,
            HALSTEAD_FILE_MESSAGE.format(
                metric=options.metric, value=value, max=options.max
            ),
            context.source.path,
            FILE_START,
            HALSTEAD_FILE_HELP,
        )


HALSTEAD_FILE = Rule(
    code=HALSTEAD_FILE_CODE,
    name=HALSTEAD_FILE_NAME,
    category="halstead",
    summary="The file does too much, by its Halstead metric.",
    options_type=HalsteadFileOptions,
    fixable=False,
    scope=Scope.FILE,
    check=check_halstead_file,
)


def check_halstead_function(
    context: RuleContext[HalsteadFunctionOptions, FileMetrics],
) -> Iterator[Diagnostic]:
    """Report a function whose Halstead metric is above ``max``.

    Nested functions count in their parent and are also evaluated alone (A13).
    """
    options = context.options
    for function in context.metrics.functions:
        value = metric_value(function.halstead, options.metric)
        if value > options.max:
            yield Diagnostic(
                HALSTEAD_FUNCTION_CODE,
                HALSTEAD_FUNCTION_NAME,
                HALSTEAD_FUNCTION_MESSAGE.format(
                    name=function.name,
                    metric=options.metric,
                    value=value,
                    max=options.max,
                ),
                context.source.path,
                function.span,
                HALSTEAD_FUNCTION_HELP,
            )


HALSTEAD_FUNCTION = Rule(
    code=HALSTEAD_FUNCTION_CODE,
    name=HALSTEAD_FUNCTION_NAME,
    category="halstead",
    summary="The function does too much, by its Halstead metric.",
    options_type=HalsteadFunctionOptions,
    fixable=False,
    scope=Scope.LINE,
    check=check_halstead_function,
)


def check_cognitive_complexity(
    context: RuleContext[CognitiveComplexityOptions, FileMetrics],
) -> Iterator[Diagnostic]:
    """Report a function whose cognitive complexity is above ``max``.

    A nested function counts in its parent and is not evaluated alone (A13).
    """
    limit = context.options.max
    for function in context.metrics.functions:
        if not function.nested and function.cognitive > limit:
            yield Diagnostic(
                COGNITIVE_CODE,
                COGNITIVE_NAME,
                COGNITIVE_MESSAGE.format(
                    name=function.name, value=function.cognitive, max=limit
                ),
                context.source.path,
                function.span,
                COGNITIVE_HELP,
            )


COGNITIVE_COMPLEXITY = Rule(
    code=COGNITIVE_CODE,
    name=COGNITIVE_NAME,
    category="complexity",
    summary="The function is too hard to follow, by its cognitive complexity.",
    options_type=CognitiveComplexityOptions,
    fixable=False,
    scope=Scope.LINE,
    check=check_cognitive_complexity,
)
