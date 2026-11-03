"""Chains above the limit."""

from os import path


def called(a: object) -> object:
    return a.b.c.d.do()


def rooted_at_self(self: object) -> object:
    return self.repo.session.engine.pool.size


def from_import() -> object:
    return path.join.__name__.upper.__doc__


def subscript(a: object) -> object:
    return a.b[0].c.d.e


def after_call(a: object) -> object:
    return a.b().c.d.e.f


def in_index(a: object, b: object) -> object:
    return a[b.c.d.e.f]
