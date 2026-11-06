"""Find the direct and indirect callees of a function, method or class using ty."""

import dataclasses
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pydantic

from ._find_callers import (
    CallHierarchyItem,
    RawItem,
    item_location,
    prepare_call_hierarchy,
    prepare_call_hierarchy_many,
)
from ._lsp import ResponseError
from ._ty_lsp import TyLSP
from ._utils import Error, Frozen, Location, LspRange, Result, to_location


class CalleeQuery(Location):
    """The position of a function, method or class (a definition or a usage)."""


class Callee(Frozen):
    """A function, method or class that ``caller`` calls."""

    name: str
    location: Location
    """Where the callee is defined (the position of its name)."""
    caller: Location
    """Where the calling function is defined (the position of its name)."""
    call_sites: tuple[Location, ...]
    """Where in the caller the callee is called."""


class _OutgoingCall(pydantic.BaseModel):
    from_ranges: list[LspRange] = pydantic.Field(alias="fromRanges")


_OUTGOING_CALLS = pydantic.TypeAdapter(list[dict[str, Any]])


@dataclasses.dataclass(frozen=True)
class CalleeEdge:
    callee: Callee
    item: RawItem
    """The callee as a call hierarchy item, to find *its* callees with."""


def _edges(caller: RawItem, outgoing: Any) -> list[CalleeEdge]:
    """Turn an ``outgoingCalls`` response for ``caller`` into one edge per callee."""
    caller_item = CallHierarchyItem.model_validate(caller)
    caller_location = to_location(caller_item.uri, caller_item.selection_range.start)
    # Keyed by the callee's definition so a callee listed more than once is merged
    # (dicts keep insertion order).
    merged: dict[Location, tuple[RawItem, CallHierarchyItem, dict[Location, None]]] = {}
    for call in _OUTGOING_CALLS.validate_python(outgoing or []):
        raw_callee: RawItem = call["to"]
        callee_item = CallHierarchyItem.model_validate(raw_callee)
        location = to_location(callee_item.uri, callee_item.selection_range.start)
        _, _, call_sites = merged.setdefault(location, (raw_callee, callee_item, {}))
        for r in _OutgoingCall.model_validate(call).from_ranges:
            # The ranges are inside the caller, so in the caller's file.
            call_sites[to_location(caller_item.uri, r.start)] = None
    return [
        CalleeEdge(
            callee=Callee(
                name=callee_item.name,
                location=location,
                caller=caller_location,
                call_sites=tuple(call_sites),
            ),
            item=raw_callee,
        )
        for location, (raw_callee, callee_item, call_sites) in merged.items()
    ]


def outgoing_callees(lsp: TyLSP, caller: RawItem) -> list[CalleeEdge]:
    """The direct callees of ``caller``, one entry per distinct callee.

    Raises ``ResponseError`` or ``pydantic.ValidationError`` on failure.
    """
    return _edges(caller, lsp.request("callHierarchy/outgoingCalls", {"item": caller}))


def outgoing_callees_many(
    lsp: TyLSP, callers: Sequence[RawItem]
) -> list[list[CalleeEdge]]:
    """Like ``outgoing_callees`` for many callers at once, in the same order.

    Raises ``ResponseError`` or ``pydantic.ValidationError`` on failure.
    """
    responses = lsp.request_many(
        "callHierarchy/outgoingCalls", [{"item": caller} for caller in callers]
    )
    return [_edges(caller, r) for caller, r in zip(callers, responses, strict=True)]


def find_direct_callees(lsp: TyLSP, query: CalleeQuery) -> Result[tuple[Callee, ...]]:
    """Return every function, method and class directly called by the one at ``query``.

    Only calls written in its own body are returned (not what those call). Each
    callee appears once, with its call sites merged. Callees can be anywhere,
    including the standard library and installed packages. Per-query failures are
    returned as ``Error``; a crashed server raises ``RuntimeError``.
    """
    try:
        return tuple(
            edge.callee
            for item in prepare_call_hierarchy(lsp, query)
            for edge in outgoing_callees(lsp, item)
        )
    except (ResponseError, pydantic.ValidationError) as exc:
        return Error(str(exc), exc)


def find_all_callees(
    lsp: TyLSP,
    query: CalleeQuery,
    *,
    max_depth: int | None = None,
    within: Path | None = None,
) -> Result[tuple[Callee, ...]]:
    """Return every direct and indirect callee of the function at ``query``.

    The result is the edges of the call graph below the queried function: each
    ``Callee`` says "``caller`` calls ``location``". Edges come in breadth-first
    order (direct callees first). Each function is expanded once, so recursion,
    mutual recursion and shared callees terminate and appear once per edge.

    This can be a lot: everything a function reaches counts, including the
    standard library and installed packages. Two limits keep it in check.
    ``max_depth`` limits how many levels are followed (``1`` is the same as
    ``find_direct_callees``). ``within`` is a directory: callees outside it are
    still returned, but what they call is not looked up. The queried function
    itself is always expanded.

    If any lookup fails, that ``Error`` is returned and no partial result is. A
    crashed server raises ``RuntimeError``.
    """
    if within is not None:
        within = within.resolve()
    try:
        frontier = prepare_call_hierarchy(lsp, query)
        seen: set[Location] = {item_location(item) for item in frontier}
        edges: list[Callee] = []
        depth = 0
        while frontier and (max_depth is None or depth < max_depth):
            depth += 1
            next_frontier: list[RawItem] = []
            for callee_edges in outgoing_callees_many(lsp, frontier):
                for edge in callee_edges:
                    edges.append(edge.callee)
                    # Already-seen callees (including the queried function itself,
                    # for recursion) still get an edge but are not expanded again.
                    if edge.callee.location in seen:
                        continue
                    seen.add(edge.callee.location)
                    if within is None or edge.callee.location.path.is_relative_to(
                        within
                    ):
                        next_frontier.append(edge.item)
            frontier = next_frontier
        return tuple(edges)
    except (ResponseError, pydantic.ValidationError) as exc:
        return Error(str(exc), exc)


@dataclasses.dataclass(frozen=True)
class CalleeGraph:
    """Who calls whom, for everything reachable from some starting functions."""

    edges: Mapping[Location, tuple[Callee, ...]]
    """For each function that was looked up, its direct callees."""

    def callees_of(self, function: Location) -> tuple[Callee, ...]:
        """The direct callees of the function defined at ``function``.

        Empty for a function that was not looked up (outside ``within``, or not
        reachable from the starting functions).
        """
        return self.edges.get(function, ())

    def reachable_from(
        self, function: Location, *, max_depth: int | None = None
    ) -> tuple[Callee, ...]:
        """Every direct and indirect callee of ``function``, as ``find_all_callees``.

        Edges come in breadth-first order, each function is expanded once, and
        ``max_depth`` limits the levels followed. This only reads the graph; it
        makes no requests to ty.
        """
        result: list[Callee] = []
        seen = {function}
        queue = deque([(function, 1)])
        while queue:
            current, depth = queue.popleft()
            if max_depth is not None and depth > max_depth:
                break
            for callee in self.callees_of(current):
                result.append(callee)
                if callee.location not in seen:
                    seen.add(callee.location)
                    queue.append((callee.location, depth + 1))
        return tuple(result)


def build_callee_graph(
    lsp: TyLSP, starts: Iterable[Location], *, within: Path | None = None
) -> Result[CalleeGraph]:
    """Look up the callees of ``starts`` and of everything they reach, once each.

    Use this instead of calling ``find_all_callees`` for many functions: those
    walks overlap, and here every function is looked up only once and the
    requests are sent in batches. Then ask the graph about each start with
    ``CalleeGraph.reachable_from``.

    ``starts`` are positions of functions, methods or classes. ``within`` is a
    directory: callees outside it are in the graph as callees but not looked up
    themselves, so they have no callees. A start that is not a function, method or
    class is skipped.

    If any lookup fails, that ``Error`` is returned and no partial graph is. A
    crashed server raises ``RuntimeError``.
    """
    if within is not None:
        within = within.resolve()
    try:
        frontier = [
            item
            for items in prepare_call_hierarchy_many(lsp, list(starts))
            for item in items
        ]
        seen: set[Location] = set()
        unique: list[RawItem] = []
        for item in frontier:
            if item_location(item) not in seen:
                seen.add(item_location(item))
                unique.append(item)
        frontier = unique
        graph: dict[Location, tuple[Callee, ...]] = {}
        while frontier:
            next_frontier: list[RawItem] = []
            for item, callee_edges in zip(
                frontier, outgoing_callees_many(lsp, frontier), strict=True
            ):
                graph[item_location(item)] = tuple(e.callee for e in callee_edges)
                for edge in callee_edges:
                    if edge.callee.location in seen:
                        continue
                    seen.add(edge.callee.location)
                    if within is None or edge.callee.location.path.is_relative_to(
                        within
                    ):
                        next_frontier.append(edge.item)
            frontier = next_frontier
        return CalleeGraph(edges=graph)
    except (ResponseError, pydantic.ValidationError) as exc:
        return Error(str(exc), exc)
