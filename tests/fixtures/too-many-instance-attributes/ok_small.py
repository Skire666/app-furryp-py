"""Classes within the limit of 3, and classes the rule does not measure."""

import dataclasses
import enum
import typing
import unittest


class Small:
    limit = 3
    other = 4
    third = 5
    fourth = 6

    def __init__(self) -> None:
        self.a = 1
        self.b = 2
        self.c = 3

    def total(self) -> int:
        return self.a + self.b + self.c


@dataclasses.dataclass
class Declared:
    a: int
    b: int

    def __post_init__(self) -> None:
        self.c = self.a
        self.d = self.b
        self.e = self.c
        self.f = self.d

    def total(self) -> int:
        return self.a + self.b


class Row(typing.NamedTuple):
    a: int


class Color(enum.Enum):
    RED = 1

    def paint(self) -> None:
        self.a = 1
        self.b = 2
        self.c = 3
        self.d = 4


class Accessors:
    def __init__(self) -> None:
        self.a = 1
        self.b = 2
        self.c = 3
        self.d = 4

    def __repr__(self) -> str:
        return "Accessors"

    def get_a(self) -> int:
        return self.a

    def set_b(self, value: int) -> None:
        self.b = value


class ReportTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.a = 1
        self.b = 2
        self.c = 3
        self.d = 4
