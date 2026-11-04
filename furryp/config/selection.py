"""Rule selectors: validation, command-line selection, selection per file.

Every selector names a rule (code or name), a code prefix or ``FUR`` (SPEC
§4.5). The selection of a file is ``select`` plus ``extend-select``, minus
``ignore`` and the applicable ``per-file-ignores``; ``ignore`` always wins, and
FUR000 is always selected.
"""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import PurePosixPath

from furryp.config.options import Settings
from furryp.config.schema import SchemaError, child_path
from furryp.core.discovery import path_matches
from furryp.core.errors import OptionError, UnknownRuleError
from furryp.core.registry import Registry
from furryp.rules.syntax import INVALID_SYNTAX

PER_FILE_IGNORES_KEY = "per-file-ignores"
ALWAYS_SELECTED = frozenset({INVALID_SYNTAX.code})


@dataclass(frozen=True, slots=True)
class CliSelection:
    """Selection given on the command line; ``select=None`` keeps the file's."""

    select: tuple[str, ...] | None = None
    extend_select: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()


def validate_selectors(settings: Settings, registry: Registry) -> None:
    """Raise ``SchemaError`` at the first unknown selector of ``settings``."""
    groups = {
        "select": settings.select,
        "extend-select": settings.extend_select,
        "ignore": settings.ignore,
    }
    for pattern, selectors in settings.per_file_ignores.items():
        groups[child_path(PER_FILE_IGNORES_KEY, pattern)] = selectors
    for path, selectors in groups.items():
        for index, selector in enumerate(selectors):
            try:
                registry.resolve(selector)
            except UnknownRuleError as error:
                raise SchemaError(f"{path}[{index}]", str(error)) from None


def _validate_option(option: str, selectors: Iterable[str], registry: Registry) -> None:
    """Raise ``OptionError`` at the first unknown selector of a CLI option."""
    for selector in selectors:
        try:
            registry.resolve(selector)
        except UnknownRuleError as error:
            raise OptionError(option, error) from None


def apply_cli_selection(
    settings: Settings, cli: CliSelection, registry: Registry
) -> Settings:
    """Return ``settings`` with the command-line selection applied."""
    _validate_option("--select", cli.select or (), registry)
    _validate_option("--extend-select", cli.extend_select, registry)
    _validate_option("--ignore", cli.ignore, registry)
    return replace(
        settings,
        select=settings.select if cli.select is None else cli.select,
        extend_select=settings.extend_select + cli.extend_select,
        ignore=settings.ignore + cli.ignore,
    )


def _codes(selectors: Iterable[str], registry: Registry) -> set[str]:
    """Return the codes of the rules designated by ``selectors``."""
    return {rule.code for selector in selectors for rule in registry.resolve(selector)}


def active_rules(settings: Settings, registry: Registry) -> frozenset[str]:
    """Return the codes of the rules selected for the project (SPEC §4.5), before ``per-file-ignores``."""
    selected = _codes(settings.select + settings.extend_select, registry)
    return frozenset(selected - _codes(settings.ignore, registry)) | ALWAYS_SELECTED


def file_selection(
    settings: Settings, registry: Registry, relative: PurePosixPath
) -> frozenset[str]:
    """Return the codes of the rules checked on a file (SPEC §4.5).

    ``relative`` is the path of the file relative to the project root, in
    POSIX form; a ``per-file-ignores`` pattern applies to it as an
    ``exclude`` pattern does (the file or one of its parent directories).
    """
    ignored: list[str] = []
    for pattern, selectors in settings.per_file_ignores.items():
        if path_matches((pattern,), relative):
            ignored.extend(selectors)
    active = active_rules(settings, registry)
    return frozenset(active - _codes(ignored, registry)) | ALWAYS_SELECTED
