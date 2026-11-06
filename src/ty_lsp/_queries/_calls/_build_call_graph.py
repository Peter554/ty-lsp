"""Build the call graph below many functions at once, using ty."""

from collections.abc import Sequence
from pathlib import Path

from ..._common import Frozen, Location, Result
from ..._ty_lsp import TyLSP
from .._common import (
    RawItem,
    capture,
    item_location,
    prepare_hierarchy_many,
)
from ._common import Callee, request_callees


class CallGraph(Frozen):
    """The direct callees of the functions below some starting points.

    Get the callees below each starting point with ``callees_of``.
    """

    roots: dict[Location, tuple[Location, ...]]
    """Where each query resolved to: the positions of the function names. Several if
    the name has several definitions."""
    callees: dict[Location, tuple[Callee, ...]]
    """The direct callees of every function that was expanded, by where the
    function's name is. A function that was reached but not expanded (because of
    ``max_depth`` or ``within``) is not a key."""
    max_depth: int | None
    within: Path | None

    def callees_of(self, query: Location) -> tuple[Callee, ...]:
        """Every callee below the function queried at ``query``, as ``find_all_callees``.

        The edges of the call graph in breadth-first order (direct callees first),
        every edge once, each function expanded once. ``query`` must be one of the
        locations the graph was built from.
        """
        start = self.roots[query]
        seen = set(start)
        frontier = list(start)
        edges: list[Callee] = []
        depth = 0
        while frontier and (self.max_depth is None or depth < self.max_depth):
            depth += 1
            next_frontier: list[Location] = []
            for function in frontier:
                for callee in self.callees.get(function, ()):
                    edges.append(callee)
                    # Already-seen callees (including the queried function itself,
                    # for recursion) still get an edge but are not expanded again.
                    if callee.location in seen:
                        continue
                    seen.add(callee.location)
                    if self._expands(callee.location):
                        next_frontier.append(callee.location)
            frontier = next_frontier
        return tuple(edges)

    def _expands(self, function: Location) -> bool:
        return self.within is None or function.path.is_relative_to(self.within)


def build_graph(
    lsp: TyLSP,
    queries: Sequence[Location],
    max_depth: int | None,
    within: Path | None,
) -> CallGraph:
    """``build_call_graph`` without turning failures into an ``Error``."""
    if within is not None:
        within = within.resolve()
    queries = list(dict.fromkeys(queries))
    resolved = prepare_hierarchy_many(lsp, "textDocument/prepareCallHierarchy", queries)

    roots: dict[Location, tuple[Location, ...]] = {}
    frontier: list[RawItem] = []
    seen: set[Location] = set()
    for query, items in zip(queries, resolved, strict=True):
        roots[query] = tuple(item_location(item) for item in items)
        for item in items:
            if item_location(item) not in seen:
                seen.add(item_location(item))
                frontier.append(item)

    # One level at a time across all the starting points, in one batch each. A
    # function that is below several of them is looked up once, at the first (so
    # lowest) depth it is reached at. That is enough for each starting point on its
    # own, which can only need it expanded at a depth that is not lower.
    callees: dict[Location, tuple[Callee, ...]] = {}
    depth = 0
    while frontier and (max_depth is None or depth < max_depth):
        depth += 1
        next_frontier: list[RawItem] = []
        for function, found in zip(
            frontier, request_callees(lsp, frontier), strict=True
        ):
            callees[item_location(function)] = tuple(callee for callee, _ in found)
            for callee, item in found:
                if callee.location in seen:
                    continue
                seen.add(callee.location)
                if within is None or callee.location.path.is_relative_to(within):
                    next_frontier.append(item)
        frontier = next_frontier
    return CallGraph(roots=roots, callees=callees, max_depth=max_depth, within=within)


def build_call_graph(
    lsp: TyLSP,
    queries: Sequence[Location],
    *,
    max_depth: int | None = None,
    within: Path | None = None,
) -> Result[CallGraph]:
    """Build the call graph below the functions, methods or classes at ``queries``.

    Each query is a definition or a usage. Use ``CallGraph.callees_of`` to get what
    is below each, which is the same as ``find_all_callees`` for it. Building them
    together is much faster than one by one: a function below several queries is
    looked up once, and each level is sent to the server in one batch.

    ``max_depth`` limits how many levels are followed (``1`` is the direct callees);
    ``None`` follows them all. ``within`` is a directory: callees outside it are
    still in the graph, but what they call is not looked up. The queried functions
    themselves are always expanded.

    If any lookup fails, that ``Error`` is returned and no partial graph is.
    """
    return capture(build_graph, lsp, queries, max_depth, within)
