"""Rendering of the HTML report with the templates of ``templates/`` (SPEC §12.2).

Python holds no HTML: the page and its labels live in the templates, with
``string.Template`` markers. Every value is escaped, except a fragment already
rendered from a template (``Html``).
"""

import functools
import html
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields
from importlib import resources
from pathlib import Path
from string import Template

from furryp.core.errors import ReportWriteError
from furryp.report.categories import Category, RuleRow, Share, Value
from furryp.report.files import AnalysisError
from furryp.report.model import Header, ReportModel, Summary

TEMPLATE_PACKAGE = "furryp.report"
TEMPLATE_DIRECTORY = "templates"
TEMPLATE_ENCODING = "utf-8"
STYLE_SHEET = "report.css"
REPORT_ENCODING = "utf-8"
REPORT_ENCODING_ERRORS = "replace"
REPORT_NEWLINE = "\n"
NOT_AVAILABLE = "\N{EN DASH}"
NOT_RATED = "*"
NOT_RATED_CLASS = "none"
LINE = "\n"


@dataclass(frozen=True, slots=True)
class Html:
    """A fragment rendered from a template: it is not escaped again."""

    text: str


type Filler = Value | Html


def read_template(name: str) -> str:
    """Return the text of a template, without its final line end."""
    path = resources.files(TEMPLATE_PACKAGE).joinpath(TEMPLATE_DIRECTORY, name)
    return path.read_text(encoding=TEMPLATE_ENCODING).rstrip(LINE)


@functools.cache
def _template(name: str) -> Template:
    """Return the template ``{name}.html``, read once."""
    return Template(read_template(f"{name}.html"))


def format_value(value: Value) -> str:
    """Return a value as displayed, before escaping."""
    if value is None:
        return NOT_AVAILABLE
    if isinstance(value, Share):
        if not value.whole:
            return NOT_AVAILABLE
        return f"{value.value:.1%} ({value.part}/{value.whole})"
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return value


def _display(value: Filler) -> str:
    """Return the text put in a template: every value but ``Html`` is escaped."""
    return value.text if isinstance(value, Html) else html.escape(format_value(value))


def fill(name: str, values: Mapping[str, Filler]) -> Html:
    """Return the template ``{name}.html`` filled with ``values``."""
    shown = {key: _display(value) for key, value in values.items()}
    return Html(_template(name).substitute(shown))


def _lines(fragments: Iterable[Html]) -> Html:
    """Return fragments, one per line."""
    return Html(LINE.join(fragment.text for fragment in fragments))


def _values_of(item: Header | Summary | AnalysisError | RuleRow) -> dict[str, Value]:
    """Return the fields of a value object, by name."""
    return {field.name: getattr(item, field.name) for field in fields(item)}


def _rating(category: Category) -> tuple[str, str]:
    """Return the text and the style of the rating of a category."""
    if category.rating is None:
        return NOT_RATED, NOT_RATED_CLASS
    return category.rating, category.rating


def _status(category: Category) -> Html:
    """Return the sentence under the title: the share, or why there is no rating."""
    if category.not_rated is not None:
        return fill(category.not_rated, {})
    return fill("rated", {"share": category.share})


def _rules_table(category: Category) -> Html:
    """Return the table of the violations per rule."""
    rows = (fill("rule_row", _values_of(row)) for row in category.rules)
    return fill("rules_table", {"rows": _lines(rows)})


def _empty_worst_files(category: Category, rows: list[Html]) -> Html:
    """Return the sentence under an empty table of worst files.

    There is none if the category is not rated, as saying that no file is in violation would claim a clean result.
    """
    if rows or category.not_rated is not None:
        return Html("")
    return fill("no_worst_files", {})


def _render_category(category: Category) -> Html:
    """Return the section of a category."""
    rating, style = _rating(category)
    rows = [fill(f"{category.key}_row", row) for row in category.worst]
    return fill(
        category.key,
        {
            **category.aggregates,
            "rating": rating,
            "rating_class": style,
            "status": _status(category),
            "rules": _rules_table(category),
            "rows": _lines(rows),
            "empty": _empty_worst_files(category, rows),
        },
    )


def _rating_cards(categories: Iterable[Category]) -> dict[str, Value]:
    """Return the placeholders of the cards of ratings of the summary."""
    values: dict[str, Value] = {}
    for category in categories:
        rating, style = _rating(category)
        values[f"{category.key}_rating"] = rating
        values[f"{category.key}_class"] = style
        rated = category.not_rated is None
        values[f"{category.key}_share"] = category.share if rated else None
    return values


def _rating_notes(categories: Iterable[Category]) -> Html:
    """Return why ratings are missing, each reason once, in a stable order."""
    reasons = {category.not_rated: None for category in categories}
    return _lines(fill(reason, {}) for reason in reasons if reason is not None)


def _render_summary(model: ReportModel) -> Html:
    """Return the section of the summary."""
    return fill(
        "summary",
        {
            **_values_of(model.summary),
            **_rating_cards(model.categories),
            "rating_notes": _rating_notes(model.categories),
        },
    )


def _error_row(error: AnalysisError) -> Html:
    """Return the line of a file in error; an internal error has no code."""
    name = "error_row" if error.code else "internal_error_row"
    return fill(name, _values_of(error))


def _render_errors(errors: tuple[AnalysisError, ...]) -> Html:
    """Return the section of the analysis errors: the complete list."""
    if not errors:
        return fill("errors", {"content": fill("no_errors", {})})
    table = fill("errors_table", {"rows": _lines(map(_error_row, errors))})
    return fill("errors", {"content": table})


def _banner(errors: tuple[AnalysisError, ...]) -> Html:
    """Return the warning of the top of the page, if a file has no measures.

    As SonarQube does: the analysis goes on, and what it could not read stays in
    sight, with a link to the details.
    """
    if not errors:
        return Html("")
    return fill("banner", {"count": len({error.path for error in errors})})


def _config_file(header: Header) -> Filler:
    """Return the configuration file, or the fragment that says there is none."""
    return header.config_file or fill("no_config_file", {})


def render_report(model: ReportModel) -> str:
    """Return the HTML document: same model, same text (SPEC §12.2)."""
    return fill(
        "page",
        {
            **_values_of(model.header),
            "config_file": _config_file(model.header),
            "css": Html(read_template(STYLE_SHEET)),
            "banner": _banner(model.errors),
            "summary": _render_summary(model),
            "categories": _lines(map(_render_category, model.categories)),
            "errors": _render_errors(model.errors),
            "appendix": fill("appendix", {"configuration": model.configuration}),
        },
    ).text


def write_report(path: Path, text: str) -> None:
    """Write the report; missing parent directories are created, as ruff does.

    A path that cannot be encoded is replaced rather than losing the report.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            text,
            encoding=REPORT_ENCODING,
            errors=REPORT_ENCODING_ERRORS,
            newline=REPORT_NEWLINE,
        )
    except OSError as error:
        reason = error.strerror or str(error)
        raise ReportWriteError(path, reason) from error
