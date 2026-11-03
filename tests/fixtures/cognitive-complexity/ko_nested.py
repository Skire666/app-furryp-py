"""Functions over the limit of 5."""


def sum_of_primes(limit: int) -> int:
    total = 0
    for i in range(2, limit):
        for j in range(2, i):
            if i % j == 0:
                break
        else:
            total += i
    return total


class Box:
    def method(self, items: list[int]) -> int:
        for item in items:
            if item:
                while item:
                    item -= 1
        return 0


def outer(items: list[int]) -> int:
    def inner(item: int) -> int:
        if item:
            if item > 1:
                return 2
        return 0

    return inner(items[0])
