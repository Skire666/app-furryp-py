"""Validation and serialisation of option dataclasses from and to JSON (§8.3).

The JSON key of a field is its name with ``_`` replaced by ``-``. Supported
annotations: ``bool``, ``int`` (always >= 0), ``float``, ``str``, ``Literal``,
``tuple[X, ...]`` (JSON array), ``dict[str, X]`` (JSON object, replaced as a
whole), nested dataclasses (merged key by key) and unions. A union of
dataclasses takes the member named by the ``type`` key, and every key of such a
member is required; another union takes its first member that accepts the
value. A field adds a domain check
with ``field(metadata={CHECK_KEY: function})`` (``CHECK_KEY`` comes from
``core.registry``, so that rules can use it), the function returning the
problem as a string, or ``None``.
"""

import contextlib
import dataclasses
import json
import types
import typing
from collections.abc import Callable, Mapping
from typing import Any, Literal

from furryp.core.errors import did_you_mean
from furryp.core.registry import CHECK_KEY

JSON_TYPE_NAMES = (
    (bool, "boolean"),
    (int, "integer"),
    (float, "number"),
    (str, "string"),
    (list, "array"),
    (dict, "object"),
)
EXPECTED_SCALARS = {
    bool: "a boolean",
    int: "an integer",
    float: "a number",
    str: "a string",
}

TAG_KEY = "type"
JSON_INDENT = 2
MISSING_KEY = 'missing key "{key}"'

type Check = Callable[[Any], str | None]
# An annotation as ``typing.get_type_hints`` gives it: a type, an alias, a union…
type Hint = object


class SchemaError(Exception):
    """Invalid value at a key path such as ``rules.function-too-long.max-lines``."""

    def __init__(self, path: str, problem: str) -> None:
        """Prefix the problem with its key path, if any."""
        super().__init__(f"{path}: {problem}" if path else problem)


def json_key(field_name: str) -> str:
    """Return the JSON key of a dataclass field."""
    return field_name.replace("_", "-")


def child_path(parent: str, key: str) -> str:
    """Return the dotted path of ``key`` below ``parent``."""
    return f"{parent}.{key}" if parent else key


def json_type_name(value: object) -> str:
    """Return the JSON name of the type of ``value`` (``bool`` before ``int``)."""
    if value is None:
        return "null"
    for python_type, name in JSON_TYPE_NAMES:
        if isinstance(value, python_type):
            return name
    return type(value).__name__


def expect_object(value: object, path: str) -> dict[str, object]:
    """Return ``value`` if it is a JSON object, else raise ``SchemaError``."""
    if not isinstance(value, dict):
        raise SchemaError(path, f"expected an object, got {json_type_name(value)}")
    return value


def parse_dataclass[T](cls: type[T], data: object, path: str, base: T | None) -> T:
    """Return ``base`` (or the defaults of ``cls``) updated with ``data``."""
    mapping = expect_object(data, path)
    start = cls() if base is None else base
    fields = {json_key(item.name): item for item in dataclasses.fields(cls)}
    hints = typing.get_type_hints(cls)
    changes: dict[str, object] = {}
    for key, value in mapping.items():
        key_path = child_path(path, key)
        item = fields.get(key)
        if item is None:
            raise SchemaError(key_path, "unknown key" + did_you_mean(key, fields))
        current = getattr(start, item.name)
        changes[item.name] = _parse_field(
            item.metadata, hints[item.name], value, key_path, current
        )
    return dataclasses.replace(start, **changes)


def _parse_field(
    metadata: Mapping[str, Check], hint: Hint, value: object, path: str, current: object
) -> object:
    """Convert the JSON ``value`` of a field, then run its domain check."""
    parsed = parse_value(hint, value, path, current)
    check = metadata.get(CHECK_KEY)
    problem = None if check is None else check(parsed)
    if problem is not None:
        raise SchemaError(path, problem)
    return parsed


def parse_value(hint: Hint, value: object, path: str, current: object = None) -> object:
    """Convert the JSON ``value`` to the annotation ``hint``."""
    origin = typing.get_origin(hint)
    if origin is Literal:
        return _parse_literal(typing.get_args(hint), value, path)
    if origin is tuple:
        return _parse_tuple(typing.get_args(hint)[0], value, path)
    if origin is dict:
        return _parse_dict(typing.get_args(hint)[1], value, path)
    if origin is types.UnionType:
        return _parse_union(typing.get_args(hint), value, path)
    if dataclasses.is_dataclass(hint):
        return parse_dataclass(hint, value, path, current)
    return _parse_scalar(hint, value, path)


def _parse_scalar(hint: type, value: object, path: str) -> object:
    """Convert a boolean, an integer (>= 0), a number or a string."""
    if hint is float and type(value) in {int, float}:
        return float(value)
    if type(value) is not hint:
        expected = EXPECTED_SCALARS[hint]
        raise SchemaError(path, f"expected {expected}, got {json_type_name(value)}")
    if hint is int and value < 0:
        raise SchemaError(path, f"must be >= 0, got {value}")
    return value


def _parse_literal(choices: tuple[object, ...], value: object, path: str) -> object:
    """Return ``value`` if it is one of ``choices``."""
    if any(type(value) is type(choice) and value == choice for choice in choices):
        return value
    allowed = ", ".join(json.dumps(choice) for choice in choices)
    got = json.dumps(value, ensure_ascii=False)
    raise SchemaError(path, f"must be one of {allowed}, got {got}")


def _parse_tuple(item_hint: Hint, value: object, path: str) -> tuple[object, ...]:
    """Convert a JSON array to a tuple of ``item_hint``."""
    if not isinstance(value, list):
        raise SchemaError(path, f"expected an array, got {json_type_name(value)}")
    return tuple(
        parse_value(item_hint, item, f"{path}[{index}]")
        for index, item in enumerate(value)
    )


def _parse_dict(value_hint: Hint, value: object, path: str) -> dict[str, object]:
    """Convert a JSON object with free keys to a dict of ``value_hint``."""
    return {
        key: parse_value(value_hint, item, child_path(path, key))
        for key, item in expect_object(value, path).items()
    }


def _parse_union(members: tuple[Hint, ...], value: object, path: str) -> object:
    """Convert ``value`` to a member of a union; if none accepts it, the error is that of the last member."""
    if all(dataclasses.is_dataclass(member) for member in members):
        return _parse_tagged(members, value, path)
    for member in members[:-1]:
        with contextlib.suppress(SchemaError):
            return parse_value(member, value, path)
    return parse_value(members[-1], value, path)


def _parse_tagged(members: tuple[Any, ...], value: object, path: str) -> object:
    """Convert a JSON object to the dataclass named by its ``type`` key.

    The name of a member is the default value of its ``type`` field.
    """
    mapping = expect_object(value, path)
    if TAG_KEY not in mapping:
        raise SchemaError(path, MISSING_KEY.format(key=TAG_KEY))
    tags = {member().type: member for member in members}
    tag = _parse_literal(tuple(tags), mapping[TAG_KEY], child_path(path, TAG_KEY))
    member = tags[tag]
    parsed = parse_dataclass(member, mapping, path, None)
    for item in dataclasses.fields(member):
        key = json_key(item.name)
        if key not in mapping:
            raise SchemaError(path, MISSING_KEY.format(key=key))
    return parsed


def dump_value(value: object) -> object:
    """Return the JSON form of an option value (inverse of ``parse_value``)."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            json_key(item.name): dump_value(getattr(value, item.name))
            for item in dataclasses.fields(value)
        }
    if isinstance(value, tuple):
        return [dump_value(item) for item in value]
    if isinstance(value, dict):
        return {key: dump_value(item) for key, item in value.items()}
    return value


def settings_json(settings: object) -> str:
    """Return the settings as a JSON text, usable as a configuration file."""
    return json.dumps(
        dump_value(settings), indent=JSON_INDENT, sort_keys=True, ensure_ascii=False
    )
