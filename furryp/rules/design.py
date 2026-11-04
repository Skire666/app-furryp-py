"""Design rules: FUR401 too-complex-class, FUR403 demeter-chain and FUR404 too-many-instance-attributes (SPEC §11).

FUR401 and FUR404 compare the measures of ``FileMetrics`` to their maximum.

FUR403 reads the maximal chains of attribute accesses. A chain ends on its last
``.attr``: a call or a subscript that follows it is not part of it. Going down
from there, ``Attribute`` adds 1, ``Subscript`` is crossed, and ``Call`` stops
the chain unless ``count-calls`` is set. What a chain does not cross (an index,
the arguments of a call, the root) is read for chains of its own.
"""

import ast
from collections.abc import Iterator
from dataclasses import dataclass

from furryp.core.ast_utils import expression_text, node_span, tree_of
from furryp.core.diagnostic import Diagnostic, truncate
from furryp.core.registry import Rule, RuleContext, Scope
from furryp.core.source import SourceFile
from furryp.metrics.file_metrics import FileMetrics

TOO_COMPLEX_CODE = "FUR401"
TOO_COMPLEX_NAME = "too-complex-class"
TOO_COMPLEX_MESSAGE = "Class `{name}` is too complex ({value} > {max})"
TOO_COMPLEX_HELP = "Move a group of related methods to a new class"
MANY_ATTRIBUTES_CODE = "FUR404"
MANY_ATTRIBUTES_NAME = "too-many-instance-attributes"
MANY_ATTRIBUTES_MESSAGE = "Class `{name}` has too many attributes ({value} > {max})"
MANY_ATTRIBUTES_HELP = (
    "Group the attributes that always go together in a separate object"
)
DEMETER_CODE = "FUR403"
DEMETER_NAME = "demeter-chain"
DEMETER_MESSAGE = "Attribute chain `{chain}` is too deep ({depth} > {max})"
DEMETER_HELP = (
    "Long chains depend on the inner structure of other objects; "
    "consider asking the first object for what you need"
)
EXPRESSION_MAX_LENGTH = 60
DEFAULT_IGNORED_ROOTS = ("self", "cls")


@dataclass(frozen=True, slots=True)
class TooComplexClassOptions:
    """Options of FUR401."""

    max_class_complexity: int = 80


def check_too_complex_class(
    context: RuleContext[TooComplexClassOptions, FileMetrics],
) -> Iterator[Diagnostic]:
    """Report a class whose complexity is above the maximum."""
    limit = context.options.max_class_complexity
    for item in context.metrics.classes:
        if item.complexity_evaluated and item.complexity > limit:
            yield Diagnostic(
                TOO_COMPLEX_CODE,
                TOO_COMPLEX_NAME,
                TOO_COMPLEX_MESSAGE.format(
                    name=item.name, value=item.complexity, max=limit
                ),
                context.source.path,
                item.span,
                TOO_COMPLEX_HELP,
            )


TOO_COMPLEX_CLASS = Rule(
    code=TOO_COMPLEX_CODE,
    name=TOO_COMPLEX_NAME,
    category="design",
    summary="The class holds too much logic: its methods add up to too much.",
    options_type=TooComplexClassOptions,
    fixable=False,
    scope=Scope.LINE,
    check=check_too_complex_class,
)


@dataclass(frozen=True, slots=True)
class TooManyInstanceAttributesOptions:
    """Options of FUR404."""

    max_instance_attributes: int = 20


def check_too_many_instance_attributes(
    context: RuleContext[TooManyInstanceAttributesOptions, FileMetrics],
) -> Iterator[Diagnostic]:
    """Report a class that assigns too many instance attributes."""
    limit = context.options.max_instance_attributes
    for item in context.metrics.classes:
        if item.attributes_evaluated and item.instance_attributes > limit:
            yield Diagnostic(
                MANY_ATTRIBUTES_CODE,
                MANY_ATTRIBUTES_NAME,
                MANY_ATTRIBUTES_MESSAGE.format(
                    name=item.name, value=item.instance_attributes, max=limit
                ),
                context.source.path,
                item.span,
                MANY_ATTRIBUTES_HELP,
            )


TOO_MANY_INSTANCE_ATTRIBUTES = Rule(
    code=MANY_ATTRIBUTES_CODE,
    name=MANY_ATTRIBUTES_NAME,
    category="design",
    summary="The class keeps too much state: it assigns too many attributes.",
    options_type=TooManyInstanceAttributesOptions,
    fixable=False,
    scope=Scope.LINE,
    check=check_too_many_instance_attributes,
)


@dataclass(frozen=True, slots=True)
class DemeterChainOptions:
    """Options of FUR403."""

    max_depth: int = 3
    ignore_roots: tuple[str, ...] = DEFAULT_IGNORED_ROOTS
    ignore_imported_modules: bool = True
    count_calls: bool = False


@dataclass(frozen=True, slots=True)
class Chain:
    """A maximal chain: its outermost node, its root and the number of attributes.

    ``branches`` is what it does not cross.
    """

    node: ast.Attribute
    root: ast.expr
    attributes: int
    branches: tuple[ast.AST, ...]

    @property
    def root_name(self) -> str | None:
        """The name at the root of the chain, ``None`` for another expression."""
        return self.root.id if isinstance(self.root, ast.Name) else None


def read_chain(node: ast.Attribute, count_calls: bool) -> Chain:
    """Return the chain whose outermost node is ``node``."""
    attributes = 0
    branches: list[ast.AST] = []
    current: ast.expr = node
    while True:
        if isinstance(current, ast.Attribute):
            attributes += 1
            current = current.value
        elif isinstance(current, ast.Subscript):
            branches.append(current.slice)
            current = current.value
        elif count_calls and isinstance(current, ast.Call):
            branches += [*current.args, *current.keywords]
            current = current.func
        else:
            return Chain(node, current, attributes, (*branches, current))


def maximal_chains(tree: ast.Module, count_calls: bool) -> Iterator[Chain]:
    """Yield every maximal chain of ``tree``, once each.

    The walk uses a stack: a chain can be deeper than the recursion limit.
    """
    stack: list[ast.AST] = [tree]
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Attribute):
            chain = read_chain(node, count_calls)
            yield chain
            stack.extend(chain.branches)
        else:
            stack.extend(ast.iter_child_nodes(node))


def _short_text(source: SourceFile, node: ast.expr) -> str:
    """Return the text of an expression, as cited by a message or a help."""
    return truncate(expression_text(source, node), EXPRESSION_MAX_LENGTH)


def check_demeter_chain(
    context: RuleContext[DemeterChainOptions],
) -> Iterator[Diagnostic]:
    """Report a maximal chain deeper than ``max-depth``."""
    options, source = context.options, context.source
    modules = context.imports.modules if options.ignore_imported_modules else ()
    for chain in maximal_chains(tree_of(source), options.count_calls):
        root = chain.root_name
        if root in modules:
            continue
        exempt = 1 if root in options.ignore_roots else 0
        depth = chain.attributes - exempt
        if depth > options.max_depth:
            text = _short_text(source, chain.node)
            yield Diagnostic(
                DEMETER_CODE,
                DEMETER_NAME,
                DEMETER_MESSAGE.format(chain=text, depth=depth, max=options.max_depth),
                source.path,
                node_span(source, chain.node),
                DEMETER_HELP,
            )


DEMETER_CHAIN = Rule(
    code=DEMETER_CODE,
    name=DEMETER_NAME,
    category="design",
    summary="An attribute chain reaches through too many objects.",
    options_type=DemeterChainOptions,
    fixable=False,
    scope=Scope.LINE,
    check=check_demeter_chain,
)
