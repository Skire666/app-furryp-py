"""Functions within the limit of 5."""


def route(event: object) -> object:
    match event:
        case {"type": "click", "x": x} if x > 0:
            return x
        case int() as code:
            return code
        case _:
            return None


def outer(flag: bool) -> object:
    def inner(value: int) -> int:
        if value:
            return 1
        return 0

    return inner if flag else None
