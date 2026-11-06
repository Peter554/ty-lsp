"""Find the direct and indirect callees of a function, method or class using ty."""

from pathlib import Path

from ..._common import Location, Result
from ..._ty_lsp import TyLSP
from .._common import capture
from ._build_call_graph import build_graph
from ._common import Callee


def _find(
    lsp: TyLSP, query: Location, max_depth: int | None, within: Path | None
) -> tuple[Callee, ...]:
    return build_graph(lsp, [query], max_depth, within).callees_of(query)


def find_direct_callees(lsp: TyLSP, query: Location) -> Result[tuple[Callee, ...]]:
    """Return what the function, method or class at ``query`` calls directly.

    ``query`` is a definition or a usage. Only calls written in its own body are
    returned (not what those call). Each callee appears once, with its call sites
    merged. Callees can be anywhere,
    including the standard library and installed packages.
    """
    return capture(_find, lsp, query, 1, None)


def find_all_callees(
    lsp: TyLSP,
    query: Location,
    *,
    max_depth: int | None = None,
    within: Path | None = None,
) -> Result[tuple[Callee, ...]]:
    """Return every direct and indirect callee of the function, method or class at
    ``query`` (a definition or a usage).

    The result is the edges of the call graph below the queried function: each
    ``Callee`` says "``caller`` calls ``location``". Edges come in breadth-first
    order (direct callees first). Each function is expanded once, so recursion,
    mutual recursion and shared callees terminate, but every edge is returned.

    This can be a lot: everything a function reaches counts, including the
    standard library and installed packages. Two limits keep it in check.
    ``max_depth`` limits how many levels are followed (``1`` is the same as
    ``find_direct_callees``). ``within`` is a directory: callees outside it are
    still returned, but what they call is not looked up. The queried function
    itself is always expanded.
    """
    return capture(_find, lsp, query, max_depth, within)
