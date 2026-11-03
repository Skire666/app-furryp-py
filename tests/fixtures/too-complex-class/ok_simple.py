"""Classes within the limit of 6, and classes the rule does not measure."""

import unittest


class Small:
    def load(self, items: list[int]) -> int:
        total = 0
        for item in items:
            if item > 0:
                total += item
        return total

    def close(self) -> None:
        pass


class Boundary:
    def load(self, items: list[int]) -> int:
        total = 0
        for item in items:
            if item > 0:
                total += item
        return total

    def render(self, flag: bool, other: bool) -> str:
        if flag:
            return "a"
        if other:
            return "b"
        return "c"


class Enclosing:
    def build(self, flag: bool) -> object:
        class Local:
            def run(self, items: list[int]) -> int:
                total = 0
                for item in items:
                    if item > 0:
                        total += item
                while total > 3:
                    total -= 1
                for item in items:
                    total += item
                if total:
                    total = 0
                return total

        if flag:
            return Local()
        return None


class ReportTestCase(unittest.TestCase):
    def test_load(self) -> None:
        for flag in (True, False):
            if flag:
                self.fail("a")
            elif not flag:
                self.fail("b")
            while flag:
                flag = False
            if flag:
                self.fail("c")
            if not flag:
                self.fail("d")


class TestReport:
    def test_load(self) -> None:
        for flag in (True, False):
            if flag:
                raise ValueError
            if not flag:
                raise KeyError
            while flag:
                flag = False
            if flag:
                raise IndexError
            if not flag:
                raise OSError


class Handlers:
    def handle_a(self, flag: bool) -> int:
        return 1 if flag else 2

    def handle_b(self, flag: bool) -> int:
        if flag:
            return 1
        return 2

    def handle_c(self, flag: bool) -> int:
        if flag:
            return 1
        return 2

    def run(self, flag: bool) -> int:
        if flag:
            return 1
        return 2

    def stop(self) -> None:
        pass
