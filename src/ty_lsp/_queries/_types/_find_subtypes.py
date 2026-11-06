"""Find the direct and indirect subtypes of a class in the project, using ty."""

from ..._common import Frozen, Location, Result
from ..._ty_lsp import TyLSP
from .._common import capture
from ._common import Edge, walk_subtypes


class Subtype(Frozen):
    """A class that is a subtype of ``supertype``."""

    name: str
    location: Location
    """Where the subtype is defined (the position of its name)."""
    supertype: Location
    """Where the supertype is defined (the position of its name)."""


def _subtypes(edges: list[Edge]) -> tuple[Subtype, ...]:
    return tuple(
        Subtype(name=e.name, location=e.location, supertype=e.origin) for e in edges
    )


def _find(lsp: TyLSP, query: Location, max_depth: int | None) -> tuple[Subtype, ...]:
    return _subtypes(walk_subtypes(lsp, query, max_depth))


def find_direct_subtypes(lsp: TyLSP, query: Location) -> Result[tuple[Subtype, ...]]:
    """Return the direct subtypes of the class at ``query``.

    Subtypes are the classes that inherit from it directly. Only those defined in
    the project are found, not those in the standard library or installed packages.
    ``query`` can also be a name whose inferred type is a class. The result is
    empty if there is no class at that position.
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

    Only subtypes defined in the project are found, not those in the standard
    library or installed packages.

    ``max_depth`` limits how many levels are followed (``1`` is the same as
    ``find_direct_subtypes``); ``None`` follows them all.
    """
    return capture(_find, lsp, query, max_depth)
