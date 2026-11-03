"""Functions within the limit of 3 lines of code."""


def documented(x: int) -> int:
    """A docstring, a comment and blank lines do not count."""
    # a comment

    y = x + 1
    z = y + 1
    return z


def folded_signature(
    first: int,
    second: int,
) -> int:
    return first + second
