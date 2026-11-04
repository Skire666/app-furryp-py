"""Design rule FUR402 layer-violation: contracts on imports (SPEC §11).

A contract tells whether a module may import a target (``core.project``), and
the messages cite the concrete modules, a ``*`` being replaced by what it
matched: ``app.billing`` must not import ``app.shipping``.

For ``forbidden``, the first pattern written that matches a target is cited, an
order that TID251 of ruff 0.17.3 does not follow (SPEC A59). For ``layers``, the pattern decides the level of the
module, not only what is cited: the most specific pattern wins, so that
``["app", "app.core"]`` does keep ``app.core`` below the rest of ``app``.

Layers are not strict: a module may import every layer below its own. The goal
is to cover the obvious cases. A rule such as "the view of an MVP never imports
the model" is a ``forbidden`` contract, tested as such.
"""

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Literal

from furryp.core.ast_utils import DOT, node_span, tree_of
from furryp.core.diagnostic import Diagnostic
from furryp.core.project import (
    WILDCARD,
    ImportTarget,
    ProjectContext,
    all_imports,
    import_targets,
    matched_prefix,
    module_matches,
)
from furryp.core.registry import Rule, RuleContext, Scope, options_of

LAYER_VIOLATION_CODE = "FUR402"
LAYER_VIOLATION_NAME = "layer-violation"
MESSAGE = "Import of `{target}` breaks contract `{contract}`: `{source}` must not import `{forbidden}`"
LAYERS_HELP = "A layer only imports the layers below it; consider inverting this dependency"
FORBIDDEN_HELP = "This dependency is forbidden; consider moving the shared code or inverting it"
INDEPENDENCE_HELP = "These modules must stay independent; consider moving the shared code to a common module"
DEFAULT_SOURCE_ROOTS = (".",)

LAYER = str | tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Breach:
    """What a module must not import, with the help of the contract it breaks."""

    source: str
    forbidden: str
    help: str


def _first_match(patterns: Sequence[str], module: str) -> str | None:
    """Return the first pattern that matches ``module``."""
    return next((item for item in patterns if module_matches(item, module)), None)


@dataclass(frozen=True, slots=True)
class ForbiddenContract:
    """No module of ``source`` imports a module of ``forbidden``."""

    type: Literal["forbidden"] = "forbidden"
    name: str = ""
    source: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()

    def breach(self, module: str, target: ImportTarget) -> Breach | None:
        """Return what ``module`` breaks by importing ``target``, if anything."""
        source = _first_match(self.source, module)
        forbidden = next((item for item in self.forbidden if target.matched_by(item)), None)
        if source is None or forbidden is None:
            return None
        return Breach(matched_prefix(source, module), matched_prefix(forbidden, target.name), FORBIDDEN_HELP)


def _layer_patterns(layer: LAYER) -> tuple[str, ...]:
    """Return the patterns of a layer, a sublist being one level."""
    return (layer,) if isinstance(layer, str) else layer


def _specificity(pattern: str) -> tuple[int, int]:
    """Return what makes a pattern specific: more segments, then fewer jokers."""
    return pattern.count(DOT), -pattern.count(WILDCARD)


def _level_of(layers: Sequence[LAYER], matches: Callable[[str], bool]) -> tuple[int, str] | None:
    """Return the level and the pattern of a module.

    The pattern is the most specific one accepted by ``matches``, the highest layer in a tie.
    """
    found = [
        (level, pattern) for level, layer in enumerate(layers) for pattern in _layer_patterns(layer) if matches(pattern)
    ]
    return max(found, key=lambda item: _specificity(item[1]), default=None)


@dataclass(frozen=True, slots=True)
class LayersContract:
    """From the highest layer to the lowest: a module never imports a layer above its own.

    A sublist is one level, and other modules are free.
    """

    type: Literal["layers"] = "layers"
    name: str = ""
    layers: tuple[LAYER, ...] = ()

    def breach(self, module: str, target: ImportTarget) -> Breach | None:
        """Return what ``module`` breaks by importing ``target``, if anything."""
        own = _level_of(self.layers, partial(module_matches, module=module))
        other = _level_of(self.layers, target.matched_by)
        if own is None or other is None or other[0] >= own[0]:
            return None
        return Breach(matched_prefix(own[1], module), matched_prefix(other[1], target.name), LAYERS_HELP)


@dataclass(frozen=True, slots=True)
class IndependenceContract:
    """None of ``modules`` imports another.

    With a ``*``, each module it matches counts apart, and a module may import what is below itself.
    """

    type: Literal["independence"] = "independence"
    name: str = ""
    modules: tuple[str, ...] = ()

    def breach(self, module: str, target: ImportTarget) -> Breach | None:
        """Return what ``module`` breaks by importing ``target``, if anything."""
        pattern = _first_match(self.modules, module)
        if pattern is None:
            return None
        source = matched_prefix(pattern, module)
        for item in self.modules:
            other = matched_prefix(item, target.name)
            if target.matched_by(item) and other != source:
                return Breach(source, other, INDEPENDENCE_HELP)
        return None


@dataclass(frozen=True, slots=True)
class LayerViolationOptions:
    """Options of FUR402."""

    source_roots: tuple[str, ...] = DEFAULT_SOURCE_ROOTS
    include_type_checking: bool = True
    contracts: tuple[ForbiddenContract | LayersContract | IndependenceContract, ...] = ()


def project_context(root: Path, rules: Mapping[str, object]) -> ProjectContext:
    """Return the project of ``root``, its source roots coming from FUR402."""
    options = options_of(rules, LAYER_VIOLATION_NAME, LayerViolationOptions)
    roots = tuple((root / item).resolve() for item in options.source_roots)
    return ProjectContext(root, roots)


def _breaches(context: RuleContext[LayerViolationOptions], module: str, target: ImportTarget) -> Iterator[Diagnostic]:
    """Yield a diagnostic per contract broken by importing ``target``."""
    for contract in context.options.contracts:
        breach = contract.breach(module, target)
        if breach is not None:
            yield Diagnostic(
                LAYER_VIOLATION_CODE,
                LAYER_VIOLATION_NAME,
                MESSAGE.format(
                    target=target.name, contract=contract.name, source=breach.source, forbidden=breach.forbidden
                ),
                context.source.path,
                node_span(context.source, target.node),
                breach.help,
            )


def check_layer_violation(context: RuleContext[LayerViolationOptions]) -> Iterator[Diagnostic]:
    """Report the imports that break a contract, at any depth of the file."""
    options, source = context.options, context.source
    module = context.project.module_of(source.path)
    if module is None or not options.contracts:
        return
    for node, guarded in all_imports(tree_of(source), context.imports):
        if options.include_type_checking or not guarded:
            for target in import_targets(node, module.package):
                yield from _breaches(context, module.name, target)


LAYER_VIOLATION = Rule(
    code=LAYER_VIOLATION_CODE,
    name=LAYER_VIOLATION_NAME,
    category="design",
    summary="An import breaks a contract between modules.",
    options_type=LayerViolationOptions,
    fixable=False,
    scope=Scope.LINE,
    check=check_layer_violation,
)
