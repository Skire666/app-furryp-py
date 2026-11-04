"""The explicit list of the shipped rules."""

from furryp.core.registry import Rule
from furryp.rules.contracts import LAYER_VIOLATION
from furryp.rules.design import DEMETER_CHAIN, TOO_COMPLEX_CLASS, TOO_MANY_INSTANCE_ATTRIBUTES
from furryp.rules.metrics import COGNITIVE_COMPLEXITY, HALSTEAD_FILE, HALSTEAD_FUNCTION
from furryp.rules.size import FILE_TOO_LONG, FUNCTION_TOO_LONG
from furryp.rules.suppression import UNUSED_FOQA
from furryp.rules.syntax import INVALID_SYNTAX

ALL_RULES: list[Rule] = [
    INVALID_SYNTAX,
    UNUSED_FOQA,
    FUNCTION_TOO_LONG,
    FILE_TOO_LONG,
    HALSTEAD_FILE,
    HALSTEAD_FUNCTION,
    COGNITIVE_COMPLEXITY,
    TOO_COMPLEX_CLASS,
    LAYER_VIOLATION,
    DEMETER_CHAIN,
    TOO_MANY_INSTANCE_ATTRIBUTES,
]
