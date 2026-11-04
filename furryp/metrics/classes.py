"""Measures of a class: complexity and instance attributes (SPEC FUR401, FUR404).

The methods of a class are the functions of its body, at any depth of its blocks
(``if``, ``try``…), so that no code goes unmeasured. Its complexity is the sum of
their cyclomatic complexities. Its instance attributes are the distinct names
assigned on the first parameter, in the methods that receive an instance: a
``@classmethod`` assigns class attributes, and a ``@staticmethod`` has no
instance.

Whether a class is a test, a dispatch or a data class is also measured here, so
that the rules and the report see the same classes.
"""

import ast
import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass

from furryp.core.ast_utils import (
    BLOCK_NODES,
    FUNCTION_TYPES,
    FunctionNode,
    docstring_of,
    name_span,
    tree_of,
)
from furryp.core.diagnostic import Span
from furryp.core.names import ImportTable, import_table
from furryp.core.source import SourceFile
from furryp.metrics.cyclomatic import cyclomatic_complexity

DOT = "."
ENUM_BASES = (
    "enum.Enum",
    "enum.IntEnum",
    "enum.StrEnum",
    "enum.Flag",
    "enum.IntFlag",
)
DUNDER = "__"
CONSTRUCTOR = "__init__"
TEST_BASE_SUFFIX = "TestCase"
TEST_CLASS_NAME = re.compile(r"Test(?:[A-Z0-9_]|$)")
DISPATCH_PREFIXES = ("visit_", "do_", "handle_", "on_")
DISPATCH_MIN_METHODS = 5
DATA_DECORATORS = frozenset(
    {
        "dataclasses.dataclass",
        "pydantic.dataclasses.dataclass",
        "attr.s",
        "attr.attrs",
        "attr.attributes",
        "attr.define",
        "attr.frozen",
        "attr.mutable",
        "attrs.define",
        "attrs.frozen",
        "attrs.mutable",
    }
)
DATA_BASES = frozenset(
    {
        "pydantic.BaseModel",
        "pydantic.BaseSettings",
        "pydantic_settings.BaseSettings",
        "typing.NamedTuple",
        "typing_extensions.NamedTuple",
        "typing.TypedDict",
        "typing_extensions.TypedDict",
        *ENUM_BASES,
    }
)
DATA_BASE_CALLS = frozenset(
    {
        "collections.namedtuple",
        "typing.NamedTuple",
        "typing_extensions.NamedTuple",
    }
)
NO_INSTANCE_DECORATORS = frozenset(
    {
        "classmethod",
        "builtins.classmethod",
        "abc.abstractclassmethod",
        "staticmethod",
        "builtins.staticmethod",
        "abc.abstractstaticmethod",
    }
)
NO_INSTANCE_METHODS = frozenset({"__new__", "__init_subclass__", "__class_getitem__"})


@dataclass(frozen=True, slots=True)
class ClassMetrics:
    """Measures of a class."""

    name: str
    span: Span
    complexity: int
    instance_attributes: int
    is_test: bool
    is_dispatch: bool
    is_data: bool

    @property
    def complexity_evaluated(self) -> bool:
        """Whether FUR401 evaluates this class: neither a test nor a dispatch class."""
        return not (self.is_test or self.is_dispatch)

    @property
    def attributes_evaluated(self) -> bool:
        """Whether FUR404 evaluates this class: neither a test nor a data class."""
        return not (self.is_test or self.is_data)


def _first_parameter(node: FunctionNode) -> str | None:
    """Return the name of the first positional parameter of a function."""
    arguments = node.args
    parameters = [*arguments.posonlyargs, *arguments.args]
    return parameters[0].arg if parameters else None


def _binds(arguments: ast.arguments, name: str) -> bool:
    """Whether ``name`` is one of the parameters of a signature."""
    parameters = (
        *arguments.posonlyargs,
        *arguments.args,
        *arguments.kwonlyargs,
        arguments.vararg,
        arguments.kwarg,
    )
    return any(item is not None and item.arg == name for item in parameters)


def _visible_children(node: ast.AST, parameter: str) -> Iterable[ast.AST]:
    """Return the children of ``node`` that can assign on ``parameter``.

    A nested function or a ``lambda`` that rebinds the name works on another
    object, as the methods of a local class do; ``self.x: T`` alone assigns
    nothing.
    """
    if isinstance(node, (*FUNCTION_TYPES, ast.Lambda)) and _binds(node.args, parameter):
        return ()
    if isinstance(node, ast.AnnAssign) and node.value is None:
        return ()
    return ast.iter_child_nodes(node)


def assigned_attributes(node: FunctionNode) -> set[str]:
    """Return the names assigned on the first parameter of a method."""
    parameter = _first_parameter(node)
    if parameter is None:
        return set()
    names: set[str] = set()
    stack: list[ast.AST] = list(node.body)
    while stack:
        current = stack.pop()
        if (
            isinstance(current, ast.Attribute)
            and isinstance(current.ctx, ast.Store)
            and isinstance(current.value, ast.Name)
            and current.value.id == parameter
        ):
            names.add(current.attr)
        stack.extend(_visible_children(current, parameter))
    return names


def _receives_instance(node: FunctionNode, imports: ImportTable) -> bool:
    """Whether the first parameter of a method of a class is an instance."""
    if node.name in NO_INSTANCE_METHODS:
        return False
    return not any(
        imports.resolve(item) in NO_INSTANCE_DECORATORS for item in node.decorator_list
    )


def _instance_attributes(
    functions: Sequence[FunctionNode], imports: ImportTable
) -> int:
    """Return the number of distinct names assigned on the instances."""
    names: set[str] = set()
    for node in functions:
        if _receives_instance(node, imports):
            names |= assigned_attributes(node)
    return len(names)


def _base_names(node: ast.ClassDef, imports: ImportTable) -> Iterator[str]:
    """Yield the resolved names of the bases (``Base[T]`` counts as ``Base``)."""
    for base in node.bases:
        plain = base.value if isinstance(base, ast.Subscript) else base
        resolved = imports.resolve(plain)
        if resolved is not None:
            yield resolved


def _is_test_class(
    node: ast.ClassDef, names: Iterable[str], imports: ImportTable
) -> bool:
    """Whether a class is a ``unittest`` test case or is collected by pytest: named ``Test…``, without ``__init__``."""
    for base in _base_names(node, imports):
        if base.rpartition(DOT)[2].endswith(TEST_BASE_SUFFIX):
            return True
    return bool(TEST_CLASS_NAME.match(node.name)) and CONSTRUCTOR not in names


def _is_dispatch_class(names: Sequence[str]) -> bool:
    """Whether at least half of at least 5 methods share a dispatch prefix."""
    if len(names) < DISPATCH_MIN_METHODS:
        return False
    return any(
        2 * sum(name.startswith(prefix) for name in names) >= len(names)
        for prefix in DISPATCH_PREFIXES
    )


def _is_known_data_class(node: ast.ClassDef, imports: ImportTable) -> bool:
    """Whether a decorator or a base is that of a known data class library."""
    for item in node.decorator_list:
        plain = item.func if isinstance(item, ast.Call) else item
        if imports.resolve(plain) in DATA_DECORATORS:
            return True
    if any(base in DATA_BASES for base in _base_names(node, imports)):
        return True
    return any(
        isinstance(base, ast.Call) and imports.resolve(base.func) in DATA_BASE_CALLS
        for base in node.bases
    )


def _is_setter_body(statement: ast.stmt, node: FunctionNode, parameter: str) -> bool:
    """Whether a statement is ``self.x = value``, ``value`` being a parameter."""
    if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
        target = statement.targets[0]
    elif isinstance(statement, ast.AnnAssign):
        target = statement.target
    else:
        return False
    value = statement.value
    return (
        _is_attribute_of(target, parameter)
        and isinstance(value, ast.Name)
        and _binds(node.args, value.id)
    )


def _is_attribute_of(node: ast.expr | None, parameter: str) -> bool:
    """Whether ``node`` is ``parameter.x``."""
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == parameter
    )


def is_accessor(node: FunctionNode) -> bool:
    """Whether a body is only ``return self.x`` or ``self.x = value``."""
    parameter = _first_parameter(node)
    body = [item for item in node.body if docstring_of(item) is None]
    if parameter is None or len(body) != 1:
        return False
    only = body[0]
    if isinstance(only, ast.Return):
        return _is_attribute_of(only.value, parameter)
    return _is_setter_body(only, node, parameter)


def _is_dunder(name: str) -> bool:
    """Whether ``name`` is ``__name__``."""
    return name.startswith(DUNDER) and name.endswith(DUNDER)


def _is_data_class(
    node: ast.ClassDef, functions: Sequence[FunctionNode], imports: ImportTable
) -> bool:
    """Whether a class is declared as data, or has no other methods than dunders and accessors."""
    return _is_known_data_class(node, imports) or all(
        _is_dunder(item.name) or is_accessor(item) for item in functions
    )


def _methods(node: ast.ClassDef) -> list[FunctionNode]:
    """Return the functions of a class body, at any depth of its blocks.

    Those of a nested function or class are not its methods.
    """
    functions: list[FunctionNode] = []
    stack: list[ast.AST] = list(node.body)
    while stack:
        current = stack.pop()
        if isinstance(current, FUNCTION_TYPES):
            functions.append(current)
        elif not isinstance(current, ast.ClassDef):
            stack.extend(
                child
                for child in ast.iter_child_nodes(current)
                if isinstance(child, BLOCK_NODES)
            )
    return functions


def _measure(
    source: SourceFile, node: ast.ClassDef, imports: ImportTable
) -> ClassMetrics:
    """Return the measures of the class ``node``."""
    functions = _methods(node)
    names = [item.name for item in functions]
    return ClassMetrics(
        name=node.name,
        span=name_span(source, node),
        complexity=sum(cyclomatic_complexity(item) for item in functions),
        instance_attributes=_instance_attributes(functions, imports),
        is_test=_is_test_class(node, names, imports),
        is_dispatch=_is_dispatch_class(names),
        is_data=_is_data_class(node, functions, imports),
    )


def class_metrics(source: SourceFile) -> tuple[ClassMetrics, ...]:
    """Return the measures of every class, at any depth, in source order."""
    tree = tree_of(source)
    imports = import_table(tree)
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    return tuple(
        _measure(source, node, imports)
        for node in sorted(classes, key=lambda item: item.lineno)
    )
