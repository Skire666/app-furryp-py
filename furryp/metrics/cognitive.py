# furryp: foqa:FUR201
"""Cognitive complexity of a function (SPEC FUR203).

An adaptation to Python of the specification by G. Ann Campbell (SonarSource):
every increment is recorded with its construct, its line and its points.

The increments of a statement come from its header, its own expressions and its
clauses, not from the blocks nested in its body. The increments listed by the
specification as instruction increments (``return``, ``try``, ``:=``…) count
only if the statement receives no other increment: this is the "no cumulation"
rule, and ``_Tally`` applies it. Recursion belongs to the function, out of this
comparison.

Expressions are walked without recursion, and an ``elif`` chain in a loop: both
can be deeper than the recursion limit, unlike the indentation of statements.
"""

import ast
import bisect
import tokenize
from collections.abc import Sequence
from dataclasses import dataclass, field

from furryp.core.ast_utils import Definition, FunctionNode, dotted_name, node_start
from furryp.core.source import SourceFile

IF = "if"
ELIF = "elif"
ELSE = "else"
FOR = "for"
WHILE = "while"
EXCEPT = "except"
MATCH = "match"
TERNARY = "ternary"
BOOLEAN_SEQUENCE = "boolean sequence"
CASE_GUARD = "case guard"
COMPREHENSION_IF = "comprehension if"
RECURSION = "recursion"
TRY = "try"
FINALLY = "finally"
WITH = "with"
WALRUS = "walrus"
INSTRUCTIONS: dict[type[ast.stmt], str] = {
    ast.Break: "break",
    ast.Continue: "continue",
    ast.Return: "return",
    ast.Assert: "assert",
    ast.Pass: "pass",
}
CLAUSE_KEYWORDS = frozenset({ELSE, FINALLY})
RECEIVERS = ("self", "cls")

type Nested = tuple[Sequence[ast.stmt], int]
type Pending = tuple[ast.AST, int, ast.AST | None]
type Loop = ast.For | ast.AsyncFor | ast.While


@dataclass(frozen=True, slots=True)
class Contribution:
    """An increment of the score: its construct, its line and its points."""

    construct: str
    line: int
    points: int


@dataclass(frozen=True, slots=True)
class ClauseKeywords:
    """Positions of the ``else`` and ``finally`` tokens of a file, sorted.

    ``ast`` does not give the line of these clauses.
    """

    positions: tuple[tuple[int, int], ...]

    def line_before(self, position: tuple[int, int]) -> int:
        """Return the line of the last keyword before ``position``."""
        return self.positions[bisect.bisect_left(self.positions, position) - 1][0]


def clause_keywords(source: SourceFile) -> ClauseKeywords:
    """Return the positions of the clause keywords of a file."""
    positions = tuple(
        token.start
        for token in source.tokens or ()
        if token.type == tokenize.NAME and token.string in CLAUSE_KEYWORDS
    )
    return ClauseKeywords(positions)


@dataclass(slots=True)
class _Tally:
    """The increments of one statement, split for the "no cumulation" rule."""

    increments: list[Contribution] = field(default_factory=list)
    instructions: list[Contribution] = field(default_factory=list)

    def add_increment(self, construct: str, line: int, points: int = 1) -> None:
        """Record an increment which replaces the instruction increments."""
        self.increments.append(Contribution(construct, line, points))

    def add_instruction(self, construct: str, line: int) -> None:
        """Record an instruction increment, worth 1."""
        self.instructions.append(Contribution(construct, line, 1))

    def kept(self) -> list[Contribution]:
        """Return the increments that count for the statement."""
        return self.increments or self.instructions


def _own_expressions(node: ast.AST) -> list[ast.AST]:
    """Return the direct children of ``node`` that are expressions."""
    return [
        child for child in ast.iter_child_nodes(node) if isinstance(child, ast.expr)
    ]


def _continues_sequence(node: ast.BoolOp, parent: ast.AST | None) -> bool:
    """Whether the parent of ``node`` is a ``BoolOp`` of the same operator."""
    return isinstance(parent, ast.BoolOp) and type(parent.op) is type(node.op)


def _tally_expression(
    node: ast.AST, level: int, parent: ast.AST | None, tally: _Tally
) -> None:
    """Record the increment of a single node of an expression."""
    match node:
        case ast.IfExp():
            tally.add_increment(TERNARY, node.lineno, 1 + level)
        case ast.BoolOp() if not _continues_sequence(node, parent):
            tally.add_increment(BOOLEAN_SEQUENCE, node.lineno)
        case ast.NamedExpr():
            tally.add_instruction(WALRUS, node.lineno)
        case ast.comprehension():
            for condition in node.ifs:
                tally.add_increment(COMPREHENSION_IF, condition.lineno)


def _child_level(node: ast.AST, child: ast.AST, level: int) -> int:
    """Return the nesting level of ``child``: operands of a ternary and the
    body of a ``lambda`` go one level deeper."""
    if isinstance(node, ast.IfExp):
        return level + 1
    if isinstance(node, ast.Lambda) and child is node.body:
        return level + 1
    return level


def _tally_expressions(roots: Sequence[ast.AST], level: int, tally: _Tally) -> None:
    """Record the increments of expressions, in the order of the source."""
    stack: list[Pending] = [(root, level, None) for root in reversed(roots)]
    while stack:
        node, depth, parent = stack.pop()
        _tally_expression(node, depth, parent, tally)
        children = [
            (child, _child_level(node, child, depth), node)
            for child in ast.iter_child_nodes(node)
        ]
        stack.extend(reversed(children))


def _scope_expressions(node: Definition) -> list[ast.AST]:
    """Return what a nested definition evaluates in the enclosing scope (§10.2).

    Annotations are left out: they are not evaluated when the ``def`` runs.
    """
    if isinstance(node, ast.ClassDef):
        keywords = [item.value for item in node.keywords]
        return [*node.decorator_list, *node.bases, *keywords]
    arguments = node.args
    defaults = [item for item in arguments.kw_defaults if item is not None]
    return [*node.decorator_list, *arguments.defaults, *defaults]


def _tally_definition(node: Definition, level: int, tally: _Tally) -> list[Nested]:
    """Record a nested definition: no increment of its own, only its content."""
    _tally_expressions(_scope_expressions(node), level, tally)
    return [(node.body, level + 1)]


def _tally_with(
    node: ast.With | ast.AsyncWith, level: int, tally: _Tally
) -> list[Nested]:
    """Record a ``with``, which does not increase the nesting of its body."""
    tally.add_instruction(WITH, node.lineno)
    for item in node.items:
        _tally_expressions(_own_expressions(item), level, tally)
    return [(node.body, level)]


def _tally_match(node: ast.Match, level: int, tally: _Tally) -> list[Nested]:
    """Record a ``match``, counted once, and the guards of its cases."""
    tally.add_increment(MATCH, node.lineno, 1 + level)
    _tally_expressions(_own_expressions(node), level, tally)
    nested: list[Nested] = []
    for case in node.cases:
        if case.guard is not None:
            tally.add_increment(CASE_GUARD, case.guard.lineno)
            _tally_expressions([case.guard], level, tally)
        nested.append((case.body, level + 1))
    return nested


def _tally_simple(node: ast.stmt, level: int, tally: _Tally) -> list[Nested]:
    """Record a statement without a block."""
    construct = INSTRUCTIONS.get(type(node))
    if construct is not None:
        tally.add_instruction(construct, node.lineno)
    _tally_expressions(_own_expressions(node), level, tally)
    return []


class _Walker:
    """Walks the statements of a function and collects their contributions."""

    def __init__(self, source: SourceFile, clauses: ClauseKeywords) -> None:
        self._source = source
        self._clauses = clauses
        self.found: list[Contribution] = []

    def walk(self, body: Sequence[ast.stmt], level: int) -> None:
        """Record the statements of ``body``, each before its nested blocks."""
        for node in body:
            tally = _Tally()
            nested = self._tally_statement(node, level, tally)
            self.found += tally.kept()
            for statements, inner in nested:
                self.walk(statements, inner)

    def _tally_statement(
        self, node: ast.stmt, level: int, tally: _Tally
    ) -> list[Nested]:
        """Record the increments of ``node`` and return its nested blocks."""
        match node:
            case ast.If():
                return self._tally_if(node, level, tally)
            case ast.For() | ast.AsyncFor() | ast.While():
                return self._tally_loop(node, level, tally)
            case ast.Try() | ast.TryStar():
                return self._tally_try(node, level, tally)
            case ast.With() | ast.AsyncWith():
                return _tally_with(node, level, tally)
            case ast.Match():
                return _tally_match(node, level, tally)
            case ast.FunctionDef() | ast.AsyncFunctionDef() | ast.ClassDef():
                return _tally_definition(node, level, tally)
            case _:
                return _tally_simple(node, level, tally)

    def _elif_of(self, node: ast.If) -> ast.If | None:
        """Return the ``If`` of the ``elif`` clause of ``node``, if any."""
        following = node.orelse[0] if node.orelse else None
        if not isinstance(following, ast.If):
            return None
        text = self._source.lines[following.lineno - 1]
        return following if text.lstrip().startswith(ELIF) else None

    def _tally_if(self, node: ast.If, level: int, tally: _Tally) -> list[Nested]:
        """Record an ``if``, its ``elif`` clauses and its ``else`` clause."""
        tally.add_increment(IF, node.lineno, 1 + level)
        _tally_expressions(_own_expressions(node), level, tally)
        nested: list[Nested] = [(node.body, level + 1)]
        while (following := self._elif_of(node)) is not None:
            node = following
            tally.add_increment(ELIF, node.lineno)
            _tally_expressions(_own_expressions(node), level, tally)
            nested.append((node.body, level + 1))
        return nested + self._tally_else(node.orelse, level, tally)

    def _tally_loop(self, node: Loop, level: int, tally: _Tally) -> list[Nested]:
        """Record a loop and its ``else`` clause."""
        construct = WHILE if isinstance(node, ast.While) else FOR
        tally.add_increment(construct, node.lineno, 1 + level)
        _tally_expressions(_own_expressions(node), level, tally)
        return [(node.body, level + 1), *self._tally_else(node.orelse, level, tally)]

    def _tally_try(
        self, node: ast.Try | ast.TryStar, level: int, tally: _Tally
    ) -> list[Nested]:
        """Record a ``try`` and its clauses; only ``except`` and ``else`` nest."""
        tally.add_instruction(TRY, node.lineno)
        nested: list[Nested] = [(node.body, level)]
        for handler in node.handlers:
            tally.add_increment(EXCEPT, handler.lineno, 1 + level)
            _tally_expressions(_own_expressions(handler), level, tally)
            nested.append((handler.body, level + 1))
        nested += self._tally_else(node.orelse, level, tally)
        if node.finalbody:
            tally.add_instruction(FINALLY, self._clause_line(node.finalbody))
            nested.append((node.finalbody, level))
        return nested

    def _tally_else(
        self, body: Sequence[ast.stmt], level: int, tally: _Tally
    ) -> list[Nested]:
        """Record the ``else`` clause of an ``if``, a loop or a ``try``, if any."""
        if not body:
            return []
        tally.add_increment(ELSE, self._clause_line(body))
        return [(body, level + 1)]

    def _clause_line(self, body: Sequence[ast.stmt]) -> int:
        """Return the line of the keyword that opens the clause ``body``."""
        first = body[0]
        decorators: list[ast.expr] = getattr(first, "decorator_list", [])
        start = decorators[0] if decorators else first
        return self._clauses.line_before(node_start(self._source, start))


def _recursion(function: FunctionNode, method: bool) -> list[Contribution]:
    """Return the increment of a function that calls itself directly, if any.

    In a method, only ``self.name(...)`` and ``cls.name(...)`` call the method:
    a bare ``name(...)`` is another function.
    """
    name = function.name
    targets = {f"{root}.{name}" for root in RECEIVERS} if method else {name}
    lines = [
        node.lineno
        for statement in function.body
        for node in ast.walk(statement)
        if isinstance(node, ast.Call) and dotted_name(node.func) in targets
    ]
    return [Contribution(RECURSION, min(lines), 1)] if lines else []


def cognitive_contributions(
    function: FunctionNode, method: bool, source: SourceFile, clauses: ClauseKeywords
) -> tuple[Contribution, ...]:
    """Return the contributions of a function, in the order of its lines."""
    walker = _Walker(source, clauses)
    walker.walk(function.body, 0)
    found = walker.found + _recursion(function, method)
    return tuple(sorted(found, key=lambda contribution: contribution.line))
