"""Classes that assign too many attributes."""


class Order:
    def __init__(self) -> None:
        self.a = 1
        self.b = 2
        self.c = 3
        self.d = 4

    def total(self) -> int:
        return self.a + self.b


class Spread:
    def __init__(self) -> None:
        self.a: int = 1
        self.b, self.c = 2, 3

    def update(self) -> None:
        self.d = 4
        self.a += 1


class Nested:
    def build(self) -> None:
        def inner() -> None:
            self.a = 1

        inner()
        self.b = 2
        self.c = 3
        self.d = 4
