"""Functions over the limit of 3 lines of code."""


def within_limit(x: int) -> int:
    y = x + 1
    z = y + 1
    return z


def over_limit(x: int) -> int:
    y = x + 1
    z = y + 1
    w = z + 1
    return w


class Box:
    def method(self, x: int) -> int:
        if x:
            x += 1
        x += 2
        return x


def outer(x: int) -> int:
    def inner(y: int) -> int:
        a = y + 1
        b = a + 1
        c = b + 1
        return c

    return inner(x)
