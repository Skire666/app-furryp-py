"""Classes whose methods add up to too much."""


class Report:
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

    def close(self) -> None:
        pass


class NotADispatch:
    def handle_a(self, flag: bool) -> int:
        if flag:
            return 1
        return 2

    def run(self, flag: bool) -> int:
        if flag:
            return 1
        return 2

    def stop(self) -> None:
        pass

    def start(self) -> None:
        pass

    def reset(self) -> None:
        pass


class Outer:
    class Inner:
        def load(self, items: list[int]) -> int:
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

        def close(self) -> None:
            pass
