"""Find the direct and indirect callers of a function, method or class using ty."""

import pydantic

from ..._common import Frozen, Location, LspRange, Result, to_location
from ..._ty_lsp import TyLSP
from .._common import (
    RAW_OBJECTS,
    HierarchyItem,
    RawItem,
    capture,
    prepare_hierarchy,
    walk_breadth_first,
)


class Caller(Frozen):
    """A function, method or class whose body calls ``callee``."""

    name: str
    location: Location
    """Where the caller is defined (the position of its name)."""
    callee: Location
    """Where the called name is defined (the position of its name)."""
    call_sites: tuple[Location, ...]
    """Where in the caller the callee is called."""


class _IncomingCall(pydantic.BaseModel):
    from_: HierarchyItem = pydantic.Field(alias="from")
    from_ranges: list[LspRange] = pydantic.Field(alias="fromRanges")


def _callers(callee: RawItem, incoming: object) -> list[tuple[Caller, RawItem]]:
    """Turn an ``incomingCalls`` response for ``callee`` into one caller per definition.

    Each caller comes with its hierarchy item, to find *its* callers with.
    """
    callee_location = HierarchyItem.model_validate(callee).location
    # Keyed by the caller's definition so a caller listed more than once is merged
    # (dicts keep insertion order).
    merged: dict[Location, tuple[RawItem, HierarchyItem, dict[Location, None]]] = {}
    for raw_call in RAW_OBJECTS.validate_python(incoming or []):
        call = _IncomingCall.model_validate(raw_call)
        _, _, call_sites = merged.setdefault(
            call.from_.location, (raw_call["from"], call.from_, {})
        )
        for r in call.from_ranges:
            # The ranges are inside the caller, so in the caller's file.
            call_sites[to_location(call.from_.uri, r.start)] = None
    return [
        (
            Caller(
                name=item.name,
                location=location,
                callee=callee_location,
                call_sites=tuple(call_sites),
            ),
            raw,
        )
        for location, (raw, item, call_sites) in merged.items()
    ]


def _expand(lsp: TyLSP, callees: list[RawItem]) -> list[list[tuple[Caller, RawItem]]]:
    """The direct callers of each callee, in the same order. Sends one batch."""
    responses = lsp._request_many(
        "callHierarchy/incomingCalls", [{"item": callee} for callee in callees]
    )
    return [_callers(callee, r) for callee, r in zip(callees, responses, strict=True)]


def _find(lsp: TyLSP, query: Location, max_depth: int | None) -> tuple[Caller, ...]:
    start = prepare_hierarchy(lsp, "textDocument/prepareCallHierarchy", query)
    return tuple(
        walk_breadth_first(
            start, lambda items: _expand(lsp, items), max_depth=max_depth
        )
    )


def find_direct_callers(lsp: TyLSP, query: Location) -> Result[tuple[Caller, ...]]:
    """Return every direct caller of the function, method or class at ``query``.

    ``query`` is a definition or a usage.

    Only direct calls are returned (not callers of callers). A caller appears
    once per definition of the name it calls, with its call sites merged.
    """
    return capture(_find, lsp, query, 1)


def find_all_callers(
    lsp: TyLSP, query: Location, *, max_depth: int | None = None
) -> Result[tuple[Caller, ...]]:
    """Return every direct and indirect caller of the function, method or class at
    ``query`` (a definition or a usage).

    The result is the edges of the call graph leading to the queried name: each
    ``Caller`` says "``location`` calls ``callee``". Edges come in breadth-first
    order (direct callers first). Each function is expanded once, so recursion,
    mutual recursion and shared callers terminate, but every edge is returned.

    ``max_depth`` limits how many levels of callers are followed (``1`` is the
    same as ``find_direct_callers``); ``None`` follows them all.
    """
    return capture(_find, lsp, query, max_depth)
