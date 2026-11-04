"""The four categories of the report: rating, aggregates, rules, worst files (§12.3).

A rule belongs to the category named by ``Rule.category``. Each category gives its
aggregates, the score that ranks its files and the columns of its table of worst
files. Values are stored under the name of the placeholder of the templates, so
that the labels stay in the templates (§12.2).

Only a file with a violation in the category is listed among the worst: a file
whose scores are fine is not a bad file. The files are ranked from the worst score
to the best, then the longest file first, then by path.
"""

import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from furryp.config.options import Settings
from furryp.config.selection import active_rules
from furryp.core.registry import Registry, Rule, options_of
from furryp.metrics.classes import ClassMetrics
from furryp.metrics.halstead import metric_value
from furryp.report.files import FileSummary
from furryp.rules.contracts import LAYER_VIOLATION_CODE
from furryp.rules.design import (
    DEMETER_CODE,
    TOO_COMPLEX_CLASS,
    TOO_MANY_INSTANCE_ATTRIBUTES,
    TooComplexClassOptions,
    TooManyInstanceAttributesOptions,
)
from furryp.rules.metrics import (
    COGNITIVE_COMPLEXITY,
    HALSTEAD_FILE,
    CognitiveComplexityOptions,
    HalsteadFileOptions,
)
from furryp.rules.size import FUNCTION_TOO_LONG, FunctionTooLongOptions


class NotRated(StrEnum):
    """Why a category has no rating; each value names a template fragment."""

    NO_RULE = "not_rated_no_rule"
    NO_FILE = "not_rated_no_file"


RATINGS = "ABCDE"
STATISTICS = {
    "mean": statistics.fmean,
    "median": lambda values: float(statistics.median(values)),
    "max": max,
    "total": sum,
}


@dataclass(frozen=True, slots=True)
class Share:
    """A part of a whole, shown as a percentage."""

    part: int
    whole: int

    @property
    def value(self) -> float:
        """The share between 0 and 1; 0 of nothing is 0."""
        return self.part / self.whole if self.whole else 0.0


type Value = int | float | str | Share | None
type Row = Mapping[str, Value]


@dataclass(frozen=True, slots=True)
class RuleRow:
    """A line of the table of the violations per rule."""

    code: str
    name: str
    violations: int
    files: int
    suppressed: int
    fixable: int


@dataclass(frozen=True, slots=True)
class Category:
    """A section of the report; ``key`` names its templates."""

    key: str
    rating: str | None
    not_rated: NotRated | None
    share: Share
    aggregates: Row
    rules: tuple[RuleRow, ...]
    worst: tuple[Row, ...]


@dataclass(frozen=True, slots=True)
class _Scope:
    """What a category reads.

    The measured files, the codes of its rules, the options of the rules and the
    rules that ran.
    """

    files: Sequence[FileSummary]
    codes: Sequence[str]
    rules: Mapping[str, object]
    active: frozenset[str]

    def count_if_run(self, code: str, count: int) -> int | None:
        """Return a count of violations; ``None`` if the rule did not run: 0 would claim a clean result.

        A measure does not depend on the selection (§12.1).
        """
        return count if code in self.active else None


@dataclass(frozen=True, slots=True)
class _Content:
    """What differs between two categories."""

    aggregates: Row
    score: Callable[[FileSummary], float]
    row: Callable[[FileSummary], Row]


def rating_of(share: float, thresholds: Sequence[float]) -> str:
    """Return A if ``share <= t1``, B if ``share <= t2``, and so on, else E."""
    for letter, limit in zip(RATINGS, thresholds, strict=False):
        if share <= limit:
            return letter
    return RATINGS[-1]


def stats(prefix: str, values: Sequence[float]) -> Row:
    """Return the statistics of ``values``, ``None`` for an empty sequence."""
    return {
        f"{prefix}_{name}": function(values) if values else None
        for name, function in STATISTICS.items()
    }


def _named(name: str, value: int) -> str:
    """Return a name followed by its value."""
    return f"{name} ({value})"


def _over(values: Sequence[int], limit: int) -> int:
    """Return how many ``values`` are above ``limit``."""
    return sum(value > limit for value in values)


def _size_row(file: FileSummary) -> Row:
    """Return the columns of a file in the worst files of Size."""
    longest = max(file.functions, key=lambda item: item.code_lines, default=None)
    return {
        "path": file.path,
        "lines": file.lines,
        "code_lines": file.code_lines,
        "functions": len(file.functions),
        "longest": longest and _named(longest.name, longest.code_lines),
    }


def _size(scope: _Scope) -> _Content:
    """Lines and lines of code per file, lines of code per function."""
    files = scope.files
    options = options_of(scope.rules, FUNCTION_TOO_LONG.name, FunctionTooLongOptions)
    limit = options.max_lines
    lengths = [item.code_lines for file in files for item in file.functions]
    aggregates = {
        **stats("lines", [file.lines for file in files]),
        **stats("code_lines", [file.code_lines for file in files]),
        **stats("function_lines", lengths),
        "function_limit": limit,
        "functions_over": _over(lengths, limit),
    }
    return _Content(aggregates, lambda file: file.code_lines, _size_row)


def _cognitive_sum(file: FileSummary) -> int:
    """Return the sum of the cognitive complexities of a file."""
    return sum(item.cognitive for item in file.outer_functions)


def _complexity_row(file: FileSummary) -> Row:
    """Return the columns of a file in the worst files of Complexity."""
    worst = max(file.outer_functions, key=lambda item: item.cognitive, default=None)
    return {
        "path": file.path,
        "sum": _cognitive_sum(file),
        "max": worst and worst.cognitive,
        "function": worst and _named(worst.name, worst.cognitive),
    }


def _complexity(scope: _Scope) -> _Content:
    """Cognitive complexity per function that is not nested (A13)."""
    options = options_of(
        scope.rules, COGNITIVE_COMPLEXITY.name, CognitiveComplexityOptions
    )
    values = [item.cognitive for file in scope.files for item in file.outer_functions]
    aggregates = {
        **stats("cognitive", values),
        "cognitive_limit": options.max,
        "functions_over": _over(values, options.max),
    }
    return _Content(aggregates, _cognitive_sum, _complexity_row)


def _halstead_row(file: FileSummary) -> Row:
    """Return the columns of a file in the worst files of Halstead."""
    measures = file.halstead
    return {
        "path": file.path,
        "volume": measures.volume,
        "difficulty": measures.difficulty,
        "effort": measures.effort,
        "bugs": measures.bugs,
    }


def _halstead(scope: _Scope) -> _Content:
    """Volume, difficulty, effort and bugs per file, volume per function."""
    files = scope.files
    metric = options_of(scope.rules, HALSTEAD_FILE.name, HalsteadFileOptions).metric
    measures = [file.halstead for file in files]
    aggregates = {
        **stats("volume", [item.volume for item in measures]),
        **stats("difficulty", [item.difficulty for item in measures]),
        **stats("effort", [item.effort for item in measures]),
        **stats("bugs", [item.bugs for item in measures]),
        **stats(
            "function_volume",
            [item.halstead.volume for file in files for item in file.functions],
        ),
        "metric": metric,
    }
    return _Content(
        aggregates, lambda file: metric_value(file.halstead, metric), _halstead_row
    )


def _complexities(classes: Sequence[ClassMetrics]) -> list[int]:
    """Return the complexities of the classes that FUR401 evaluates."""
    return [item.complexity for item in classes if item.complexity_evaluated]


def _attributes(classes: Sequence[ClassMetrics]) -> list[int]:
    """Return the attribute counts of the classes that FUR404 evaluates."""
    return [item.instance_attributes for item in classes if item.attributes_evaluated]


def _violations_of(files: Sequence[FileSummary], code: str) -> int:
    """Return the number of violations of a rule in the files."""
    return sum(file.violations[code] for file in files)


def _design_aggregates(scope: _Scope) -> Row:
    """Return the aggregates of the classes, of the contracts and of the chains."""
    files, rules = scope.files, scope.rules
    classes = [item for file in files for item in file.classes]
    complexities, attributes = _complexities(classes), _attributes(classes)
    complexity_limit = options_of(
        rules, TOO_COMPLEX_CLASS.name, TooComplexClassOptions
    ).max_class_complexity
    attributes_limit = options_of(
        rules, TOO_MANY_INSTANCE_ATTRIBUTES.name, TooManyInstanceAttributesOptions
    ).max_instance_attributes
    return {
        "classes": len(classes),
        **stats("complexity", complexities),
        **stats("attributes", attributes),
        "complexity_limit": complexity_limit,
        "attributes_limit": attributes_limit,
        "complexity_over": Share(
            _over(complexities, complexity_limit), len(complexities)
        ),
        "attributes_over": Share(_over(attributes, attributes_limit), len(attributes)),
        "contracts": scope.count_if_run(
            LAYER_VIOLATION_CODE, _violations_of(files, LAYER_VIOLATION_CODE)
        ),
        "chains": scope.count_if_run(DEMETER_CODE, _violations_of(files, DEMETER_CODE)),
    }


def _design(scope: _Scope) -> _Content:
    """Classes, contracts and chains; the score is the number of violations."""
    codes = scope.codes

    def row(file: FileSummary) -> Row:
        return {
            "path": file.path,
            "violations": file.count_of(codes),
            "max_complexity": max(_complexities(file.classes), default=None),
            "max_attributes": max(_attributes(file.classes), default=None),
            "contracts": scope.count_if_run(
                LAYER_VIOLATION_CODE, file.violations[LAYER_VIOLATION_CODE]
            ),
            "chains": scope.count_if_run(DEMETER_CODE, file.violations[DEMETER_CODE]),
        }

    return _Content(_design_aggregates(scope), lambda file: file.count_of(codes), row)


CONTENTS = {
    "size": _size,
    "complexity": _complexity,
    "halstead": _halstead,
    "design": _design,
}


def _rule_row(files: Sequence[FileSummary], rule: Rule) -> RuleRow:
    """Return the counts of a rule over the files."""
    code = rule.code
    return RuleRow(
        code,
        rule.name,
        sum(file.violations[code] for file in files),
        sum(bool(file.violations[code]) for file in files),
        sum(file.suppressed[code] for file in files),
        sum(file.fixable[code] for file in files),
    )


def _worst_rows(
    files: Sequence[FileSummary], codes: Sequence[str], content: _Content, limit: int
) -> tuple[Row, ...]:
    """Return the files in violation: worst score, longest file, then path."""
    flagged = [file for file in files if file.count_of(codes)]
    flagged.sort(key=lambda file: (-content.score(file), -file.lines, file.path))
    return tuple(content.row(file) for file in flagged[:limit])


def _not_rated(
    files: Sequence[FileSummary], rows: Sequence[RuleRow]
) -> NotRated | None:
    """Return why a category cannot be rated, if so: no rule ran, or no file."""
    if not rows:
        return NotRated.NO_RULE
    return None if files else NotRated.NO_FILE


def _category(
    key: str, files: Sequence[FileSummary], settings: Settings, registry: Registry
) -> Category:
    """Return a category, computed on the files that were measured."""
    rules = [rule for rule in registry.rules if rule.category == key]
    codes = [rule.code for rule in rules]
    active = active_rules(settings, registry)
    rows = tuple(_rule_row(files, rule) for rule in rules if rule.code in active)
    content = CONTENTS[key](_Scope(files, codes, settings.rules, active))
    share = Share(sum(bool(file.count_of(codes)) for file in files), len(files))
    not_rated = _not_rated(files, rows)
    options = settings.report
    return Category(
        key,
        None if not_rated else rating_of(share.value, options.rating_thresholds),
        not_rated,
        share,
        content.aggregates,
        rows,
        _worst_rows(files, codes, content, options.top_n),
    )


def build_categories(
    files: Sequence[FileSummary], settings: Settings, registry: Registry
) -> tuple[Category, ...]:
    """Return the four categories, in the order of the report."""
    return tuple(_category(key, files, settings, registry) for key in CONTENTS)
