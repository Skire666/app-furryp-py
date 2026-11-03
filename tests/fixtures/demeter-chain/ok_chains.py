"""Chains within the limit, and chains the rule exempts."""

import os
import xml.etree.ElementTree as tree


def within(a: object) -> object:
    return a.b.c.do


def self_root(self: object) -> object:
    return self.repo.session.query.all()


def imported() -> object:
    return os.path.join.__name__.upper, tree.Element.__doc__.strip.__name__


def calls(a: object) -> object:
    return a.b().c.d.e().f.g.h
