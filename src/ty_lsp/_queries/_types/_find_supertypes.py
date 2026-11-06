"""Find the direct and indirect supertypes of a class using ty."""

from ..._common import Frozen, Location, Result
from ..._ty_lsp import TyLSP
from .._common import capture
from ._common import walk_hierarchy


class Supertype(Frozen):
    """A class that is a supertype of ``subtype``."""

    name: str
    location: Location
    """Where the supertype is defined (the position of its name)."""
    subtype: Location
    """Where the subtype is defined (the position of its name)."""


def _find(lsp: TyLSP, query: Location, max_depth: int | None) -> tuple[Supertype, ...]:
    return tuple(
        Supertype(name=e.name, location=e.location, subtype=e.origin)
        for e in walk_hierarchy(lsp, query, "supertypes", max_depth)
    )


def find_direct_supertypes(
    lsp: TyLSP, query: Location
) -> Result[tuple[Supertype, ...]]:
    """Return the direct supertypes of the class at ``query``.

    Supertypes are its base classes, including ``object``, which is defined
    outside the project. ``query`` can also be a name whose inferred type is a
    class. The result is empty if there is no class at that position.
    """
    return capture(_find, lsp, query, 1)


def find_all_supertypes(
    lsp: TyLSP, query: Location, *, max_depth: int | None = None
) -> Result[tuple[Supertype, ...]]:
    """Return every direct and indirect supertype of the class at ``query``.

    The result is the edges of the inheritance graph: each ``Supertype`` says
    "``location`` is a direct supertype of ``subtype``". Edges come in breadth-first
    order. Each class is expanded once, but a class reached by several routes
    (multiple inheritance) appears once per edge.

    ``max_depth`` limits how many levels are followed (``1`` is the same as
    ``find_direct_supertypes``); ``None`` follows them all.
    """
    return capture(_find, lsp, query, max_depth)
