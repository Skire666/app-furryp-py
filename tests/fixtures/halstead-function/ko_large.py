"""Functions with too much logic for a volume of 70."""


def small(x: int) -> int:
    return x


def invoice_total(lines: list[int], discount: int) -> int:
    total = sum(line for line in lines)
    total = total - discount
    return max(total, 0)


class Box:
    def scaled(self, width: int, height: int, ratio: int) -> int:
        return self.factor * width * height * ratio


def outer(items: list[int], ratio: int) -> int:
    def inner(width: int, height: int) -> int:
        return ratio * width * height + ratio - width - height

    return inner(items[0], items[1])
