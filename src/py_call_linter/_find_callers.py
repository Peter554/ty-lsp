"""Find the direct and indirect callers of a function, method or class using ty."""

import dataclasses
from collections.abc import Sequence
from typing import Any

import pydantic

from ._lsp import ResponseError
from ._ty_lsp import TyLSP
from ._utils import Error, Frozen, Location, LspRange, Result, to_location


class CallerQuery(Location):
    """The position of a name (a definition or a usage) whose callers to find."""


class Caller(Frozen):
    """A function, method or class whose body calls ``callee``."""

    name: str
    location: Location
    """Where the caller is defined (the position of its name)."""
    callee: Location
    """Where the called name is defined (the position of its name)."""
    call_sites: tuple[Location, ...]
    """Where in the caller the callee is called."""


class CallHierarchyItem(pydantic.BaseModel):
    """The fields of a call hierarchy item that we read."""

    name: str
    uri: str
    selection_range: LspRange = pydantic.Field(alias="selectionRange")


class _IncomingCall(pydantic.BaseModel):
    from_: CallHierarchyItem = pydantic.Field(alias="from")
    from_ranges: list[LspRange] = pydantic.Field(alias="fromRanges")


_ITEMS = pydantic.TypeAdapter(list[dict[str, Any]])
_INCOMING_CALLS = pydantic.TypeAdapter(list[dict[str, Any]])

type RawItem = dict[str, Any]
"""A call hierarchy item exactly as the server sent it (it must be sent back as is)."""


@dataclasses.dataclass(frozen=True)
class CallerEdge:
    caller: Caller
    item: RawItem
    """The caller as a call hierarchy item, to find *its* callers with."""


def item_location(item: RawItem) -> Location:
    """Where the item's name is defined."""
    parsed = CallHierarchyItem.model_validate(item)
    return to_location(parsed.uri, parsed.selection_range.start)


def prepare_call_hierarchy(lsp: TyLSP, query: Location) -> list[RawItem]:
    """Resolve ``query`` to call hierarchy items (several if the name has several definitions).

    Raises ``ResponseError`` or ``pydantic.ValidationError`` on failure.
    """
    items: Any = lsp.request(
        "textDocument/prepareCallHierarchy",
        {
            "textDocument": {"uri": query.path.resolve().as_uri()},
            "position": {"line": query.line - 1, "character": query.column - 1},
        },
    )
    return _ITEMS.validate_python(items or [])


def prepare_call_hierarchy_many(
    lsp: TyLSP, queries: Sequence[Location]
) -> list[list[RawItem]]:
    """Like ``prepare_call_hierarchy`` for many queries at once, in the same order.

    Raises ``ResponseError`` or ``pydantic.ValidationError`` on failure.
    """
    responses = lsp.request_many(
        "textDocument/prepareCallHierarchy",
        [
            {
                "textDocument": {"uri": query.path.resolve().as_uri()},
                "position": {"line": query.line - 1, "character": query.column - 1},
            }
            for query in queries
        ],
    )
    return [_ITEMS.validate_python(items or []) for items in responses]


def incoming_callers(lsp: TyLSP, callee: RawItem) -> list[CallerEdge]:
    """The direct callers of ``callee``, one entry per distinct caller.

    Raises ``ResponseError`` or ``pydantic.ValidationError`` on failure.
    """
    callee_location = item_location(callee)
    incoming: Any = lsp.request("callHierarchy/incomingCalls", {"item": callee})
    # Keyed by the caller's definition so a caller listed more than once is merged
    # (dicts keep insertion order).
    merged: dict[Location, tuple[RawItem, dict[Location, None]]] = {}
    for call in _INCOMING_CALLS.validate_python(incoming or []):
        raw_caller: RawItem = call["from"]
        parsed = CallHierarchyItem.model_validate(raw_caller)
        location = to_location(parsed.uri, parsed.selection_range.start)
        _, call_sites = merged.setdefault(location, (raw_caller, {}))
        for r in _IncomingCall.model_validate(call).from_ranges:
            call_sites[to_location(parsed.uri, r.start)] = None
    return [
        CallerEdge(
            caller=Caller(
                name=CallHierarchyItem.model_validate(raw_caller).name,
                location=location,
                callee=callee_location,
                call_sites=tuple(call_sites),
            ),
            item=raw_caller,
        )
        for location, (raw_caller, call_sites) in merged.items()
    ]


def find_direct_callers(lsp: TyLSP, query: CallerQuery) -> Result[tuple[Caller, ...]]:
    """Return every direct caller of the name at ``query``.

    Only direct calls are returned (not callers of callers). A caller appears
    once per definition of the name it calls, with its call sites merged.
    Per-query failures are returned as ``Error``; a crashed server raises
    ``RuntimeError``.
    """
    try:
        return tuple(
            edge.caller
            for item in prepare_call_hierarchy(lsp, query)
            for edge in incoming_callers(lsp, item)
        )
    except (ResponseError, pydantic.ValidationError) as exc:
        return Error(str(exc), exc)


def find_all_callers(
    lsp: TyLSP, query: CallerQuery, *, max_depth: int | None = None
) -> Result[tuple[Caller, ...]]:
    """Return every direct and indirect caller of the name at ``query``.

    The result is the edges of the call graph leading to the queried name: each
    ``Caller`` says "``location`` calls ``callee``". Edges come in breadth-first
    order (direct callers first). Each function is expanded once, so recursion,
    mutual recursion and shared callers terminate and appear once per edge.

    ``max_depth`` limits how many levels of callers are followed (``1`` is the
    same as ``find_direct_callers``); ``None`` follows them all.

    If any lookup fails, that ``Error`` is returned and no partial result is. A
    crashed server raises ``RuntimeError``.
    """
    try:
        # Only the first lookup resolves a source position; after that each caller's
        # own call hierarchy item (from the previous response) is followed directly.
        frontier = prepare_call_hierarchy(lsp, query)
        seen: set[Location] = {item_location(item) for item in frontier}
        edges: list[Caller] = []
        depth = 0
        while frontier and (max_depth is None or depth < max_depth):
            depth += 1
            next_frontier: list[RawItem] = []
            for item in frontier:
                for edge in incoming_callers(lsp, item):
                    edges.append(edge.caller)
                    # Already-seen callers (including the queried name itself, for
                    # recursion) still get an edge but are not expanded again.
                    if edge.caller.location not in seen:
                        seen.add(edge.caller.location)
                        next_frontier.append(edge.item)
            frontier = next_frontier
        return tuple(edges)
    except (ResponseError, pydantic.ValidationError) as exc:
        return Error(str(exc), exc)
