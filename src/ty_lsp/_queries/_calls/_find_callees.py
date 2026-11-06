"""Find the direct and indirect callees of a function, method or class using ty."""

from pathlib import Path

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
    to: HierarchyItem
    from_ranges: list[LspRange] = pydantic.Field(alias="fromRanges")


def _callees(caller: RawItem, outgoing: object) -> list[tuple[Callee, RawItem]]:
    """Turn an ``outgoingCalls`` response for ``caller`` into one callee per definition.

    Each callee comes with its hierarchy item, to find *its* callees with.
    """
    caller_item = HierarchyItem.model_validate(caller)
    # Keyed by the callee's definition so a callee listed more than once is merged
    # (dicts keep insertion order).
    merged: dict[Location, tuple[RawItem, HierarchyItem, dict[Location, None]]] = {}
    for raw_call in RAW_OBJECTS.validate_python(outgoing or []):
        call = _OutgoingCall.model_validate(raw_call)
        _, _, call_sites = merged.setdefault(
            call.to.location, (raw_call["to"], call.to, {})
        )
        for r in call.from_ranges:
            # The ranges are inside the caller, so in the caller's file.
            call_sites[to_location(caller_item.uri, r.start)] = None
    return [
        (
            Callee(
                name=item.name,
                location=location,
                caller=caller_item.location,
                call_sites=tuple(call_sites),
            ),
            raw,
        )
        for location, (raw, item, call_sites) in merged.items()
    ]


def _expand(lsp: TyLSP, callers: list[RawItem]) -> list[list[tuple[Callee, RawItem]]]:
    """The direct callees of each caller, in the same order. Sends one batch."""
    responses = lsp._request_many(
        "callHierarchy/outgoingCalls", [{"item": caller} for caller in callers]
    )
    return [_callees(caller, r) for caller, r in zip(callers, responses, strict=True)]


def _find(
    lsp: TyLSP, query: Location, max_depth: int | None, within: Path | None
) -> tuple[Callee, ...]:
    if within is not None:
        within = within.resolve()
    start = prepare_hierarchy(lsp, "textDocument/prepareCallHierarchy", query)
    return tuple(
        walk_breadth_first(
            start,
            lambda items: _expand(lsp, items),
            max_depth=max_depth,
            expand_only=lambda loc: within is None or loc.path.is_relative_to(within),
        )
    )


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
