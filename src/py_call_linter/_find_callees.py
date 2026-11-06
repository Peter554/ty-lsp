"""Find the direct and indirect callees of a function, method or class using ty."""

import dataclasses
from pathlib import Path
from typing import Any

import pydantic

from ._find_callers import (
    CallHierarchyItem,
    RawItem,
    item_location,
    prepare_call_hierarchy,
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


def outgoing_callees(lsp: TyLSP, caller: RawItem) -> list[CalleeEdge]:
    """The direct callees of ``caller``, one entry per distinct callee.

    Raises ``ResponseError`` or ``pydantic.ValidationError`` on failure.
    """
    caller_item = CallHierarchyItem.model_validate(caller)
    caller_location = item_location(caller)
    outgoing: Any = lsp.request("callHierarchy/outgoingCalls", {"item": caller})
    # Keyed by the callee's definition so a callee listed more than once is merged
    # (dicts keep insertion order).
    merged: dict[Location, tuple[RawItem, dict[Location, None]]] = {}
    for call in _OUTGOING_CALLS.validate_python(outgoing or []):
        raw_callee: RawItem = call["to"]
        callee_item = CallHierarchyItem.model_validate(raw_callee)
        location = to_location(callee_item.uri, callee_item.selection_range.start)
        _, call_sites = merged.setdefault(location, (raw_callee, {}))
        for r in _OutgoingCall.model_validate(call).from_ranges:
            # The ranges are inside the caller, so in the caller's file.
            call_sites[to_location(caller_item.uri, r.start)] = None
    return [
        CalleeEdge(
            callee=Callee(
                name=CallHierarchyItem.model_validate(raw_callee).name,
                location=location,
                caller=caller_location,
                call_sites=tuple(call_sites),
            ),
            item=raw_callee,
        )
        for location, (raw_callee, call_sites) in merged.items()
    ]


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
            for item in frontier:
                for edge in outgoing_callees(lsp, item):
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
