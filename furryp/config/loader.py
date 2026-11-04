"""Discovery, reading and validation of the configuration (SPEC §8.1 to §8.3).

Precedence: command line, then ``furryp.json``, then the defaults of the
code. Only the existence of ``pyproject.toml`` matters (it marks the project
root): its content is never read.
"""

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import NoReturn

from furryp.config.defaults import (
    CONFIG_ENCODING,
    CONFIG_FILE_NAME,
    PYPROJECT_FILE_NAME,
)
from furryp.config.options import Settings
from furryp.config.schema import SchemaError, child_path, expect_object, parse_dataclass
from furryp.config.selection import (
    CliSelection,
    apply_cli_selection,
    validate_selectors,
)
from furryp.core.errors import ConfigError, UnknownRuleError
from furryp.core.paths import display_path
from furryp.core.registry import Registry

RULES_KEY = "rules"
NO_OPTIONS = "rule has no options"


class DuplicateKeyError(ValueError):
    """A key given twice in a JSON object."""

    def __init__(self, key: str) -> None:
        """Name the key."""
        super().__init__(f'duplicate key "{key}"')


class ForbiddenConstantError(ValueError):
    """A non-standard JSON constant: ``NaN``, ``Infinity`` or ``-Infinity``."""

    def __init__(self, constant: str) -> None:
        """Name the constant."""
        super().__init__(f"{constant} is not allowed")


@dataclass(frozen=True, slots=True)
class Configuration:
    """Effective settings, with the project root and the file they come from."""

    project_root: Path
    config_file: Path | None
    settings: Settings


def find_configuration(cwd: Path, explicit: Path | None) -> tuple[Path, Path | None]:
    """Return the project root and the configuration file to read, if any."""
    if explicit is not None:
        config_file = (cwd / explicit).resolve()
        return config_file.parent, config_file
    folders = (cwd, *cwd.parents)
    marked = (folder for folder in folders if (folder / PYPROJECT_FILE_NAME).is_file())
    root = next(marked, cwd)
    candidate = root / CONFIG_FILE_NAME
    return root, candidate if candidate.is_file() else None


def default_settings(registry: Registry) -> Settings:
    """Return the default settings, with the default options of every rule."""
    return Settings(
        rules={
            rule.name: rule.options_type()
            for rule in registry.rules
            if rule.options_type is not None
        }
    )


def load_configuration(
    cwd: Path,
    explicit: Path | None,
    registry: Registry,
    cli: CliSelection | None = None,
) -> Configuration:
    """Discover, read and validate the configuration seen from ``cwd``."""
    root, config_file = find_configuration(cwd, explicit)
    settings = default_settings(registry)
    if config_file is not None:
        settings = _load_file(config_file, cwd, settings, registry)
    settings = apply_cli_selection(settings, cli or CliSelection(), registry)
    return Configuration(root, config_file, settings)


def _load_file(path: Path, cwd: Path, base: Settings, registry: Registry) -> Settings:
    """Read ``path`` over ``base``; every problem becomes a ``ConfigError``."""
    label = display_path(path, cwd)
    try:
        return parse_settings(read_json(path), base, registry)
    except OSError as error:
        raise ConfigError(label, f"cannot read file: {error.strerror or error}") from None
    except UnicodeDecodeError:
        raise ConfigError(label, "file is not valid UTF-8") from None
    except ValueError as error:
        raise ConfigError(label, f"invalid JSON: {error}") from None
    except SchemaError as error:
        raise ConfigError(label, error) from None


def read_json(path: Path) -> object:
    """Read a JSON file in UTF-8 (BOM tolerated); duplicate keys are refused."""
    text = path.read_text(encoding=CONFIG_ENCODING)
    return json.loads(text, object_pairs_hook=_unique_keys, parse_constant=_refuse)


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Build a JSON object, refusing duplicate keys."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(key)
        result[key] = value
    return result


def _refuse(constant: str) -> NoReturn:
    """Refuse the non-standard constants ``NaN``, ``Infinity`` and ``-Infinity``."""
    raise ForbiddenConstantError(constant)


def parse_settings(data: object, base: Settings, registry: Registry) -> Settings:
    """Return ``base`` updated with the JSON configuration ``data``."""
    mapping = dict(expect_object(data, ""))
    rules_data = mapping.pop(RULES_KEY, {})
    settings = parse_dataclass(Settings, mapping, "", base)
    settings = replace(
        settings, rules=_parse_rules(rules_data, settings.rules, registry)
    )
    validate_selectors(settings, registry)
    return settings


def _parse_rules(
    data: object, base: dict[str, object], registry: Registry
) -> dict[str, object]:
    """Merge the ``rules`` object into ``base``, key by key for each rule."""
    rules = dict(base)
    for name, value in expect_object(data, RULES_KEY).items():
        path = child_path(RULES_KEY, name)
        try:
            rule = registry.by_name(name)
        except UnknownRuleError as error:
            raise SchemaError(path, str(error)) from None
        if rule.options_type is None:
            raise SchemaError(path, NO_OPTIONS)
        rules[name] = parse_dataclass(rule.options_type, value, path, rules.get(name))
    return rules
