"""Halstead metrics, counted on tokens rather than on the AST (SPEC FUR201, A09).

A pair of delimiters counts once, at its opening. ``tokenize`` gives an empty
``FSTRING_MIDDLE`` after a nested format spec (``f"{x:>{w}}"``): it holds no
text, so it is not an operand.
"""

import keyword
import math
import tokenize
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

STRING_BOUNDARY_TOKENS = frozenset(
    {tokenize.FSTRING_START, tokenize.FSTRING_END, tokenize.TSTRING_START, tokenize.TSTRING_END}
)
CLOSING_DELIMITERS = frozenset({")", "]", "}"})
MIN_VOCABULARY = 2
BUGS_DIVISOR = 3000

type Tokens = Iterable[tokenize.TokenInfo]


@dataclass(frozen=True, slots=True)
class Halstead:
    """Counts of distinct and total operators and operands, and their metrics."""

    distinct_operators: int
    distinct_operands: int
    total_operators: int
    total_operands: int

    @property
    def vocabulary(self) -> int:
        """Number of distinct operators and operands (``n``)."""
        return self.distinct_operators + self.distinct_operands

    @property
    def length(self) -> int:
        """Total number of operators and operands (``N``)."""
        return self.total_operators + self.total_operands

    @property
    def volume(self) -> float:
        """``N * log2(n)``, 0 if ``n <= 1``."""
        if self.vocabulary < MIN_VOCABULARY:
            return 0.0
        return self.length * math.log2(self.vocabulary)

    @property
    def difficulty(self) -> float:
        """``(n1 / 2) * (N2 / n2)``, 0 if ``n2 = 0``."""
        if not self.distinct_operands:
            return 0.0
        return self.distinct_operators / 2 * self.total_operands / self.distinct_operands

    @property
    def effort(self) -> float:
        """``difficulty * volume``."""
        return self.difficulty * self.volume

    @property
    def bugs(self) -> float:
        """``volume / 3000``."""
        return self.volume / BUGS_DIVISOR


def metric_value(halstead: Halstead, metric: str) -> float:
    """Return the value of ``metric``: volume, difficulty, effort or bugs."""
    return getattr(halstead, metric)


def _is_counted(token: tokenize.TokenInfo) -> bool:
    """Whether Halstead counts this significant token."""
    if token.type in STRING_BOUNDARY_TOKENS:
        return False
    if token.type == tokenize.OP:
        return token.string not in CLOSING_DELIMITERS
    return bool(token.string)


def counted_tokens(tokens: Tokens) -> tuple[tokenize.TokenInfo, ...]:
    """Return the tokens that Halstead counts among significant tokens."""
    return tuple(token for token in tokens if _is_counted(token))


def _is_operator(token: tokenize.TokenInfo) -> bool:
    """Whether a counted token is an operator: ``OP`` or a hard keyword."""
    if token.type == tokenize.NAME:
        return keyword.iskeyword(token.string)
    return token.type == tokenize.OP


def measure(tokens: Tokens) -> Halstead:
    """Return the Halstead counts of counted tokens, distinct by exact text."""
    operators: Counter[str] = Counter()
    operands: Counter[str] = Counter()
    for token in tokens:
        (operators if _is_operator(token) else operands)[token.string] += 1
    return Halstead(len(operators), len(operands), operators.total(), operands.total())
