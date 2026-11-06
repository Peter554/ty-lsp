"""Find the direct and indirect subtypes of a class using ty."""

from ..._common import Frozen, Location, Result
from ..._ty_lsp import TyLSP
from .._common import capture
from ._common import walk_hierarchy


class Subtype(Frozen):
    """A class that is a subtype of ``supertype``."""

    name: str
    location: Location
    """Where the subtype is defined (the position of its name)."""
    supertype: Location
    """Where the supertype is defined (the position of its name)."""


def _find(lsp: TyLSP, query: Location, max_depth: int | None) -> tuple[Subtype, ...]:
    return tuple(
        Subtype(name=e.name, location=e.location, supertype=e.origin)
        for e in walk_hierarchy(lsp, query, "subtypes", max_depth)
    )


def find_direct_subtypes(lsp: TyLSP, query: Location) -> Result[tuple[Subtype, ...]]:
    """Return the direct subtypes of the class at ``query``.

    Subtypes are the classes that inherit from it directly. ``query`` can also be
    a name whose inferred type is a class. The result is empty if there is no class
    at that position.
    """
    return capture(_find, lsp, query, 1)


def find_all_subtypes(
    lsp: TyLSP, query: Location, *, max_depth: int | None = None
) -> Result[tuple[Subtype, ...]]:
    """Return every direct and indirect subtype of the class at ``query``.

    The result is the edges of the inheritance graph: each ``Subtype`` says
    "``location`` is a direct subtype of ``supertype``". Edges come in breadth-first
    order. Each class is expanded once, but a class reached by several routes
    (multiple inheritance) appears once per edge.

    ``max_depth`` limits how many levels are followed (``1`` is the same as
    ``find_direct_subtypes``); ``None`` follows them all.
    """
    return capture(_find, lsp, query, max_depth)
