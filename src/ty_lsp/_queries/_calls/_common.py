"""Outgoing calls, shared by the callee queries."""

import pydantic

from ..._common import Frozen, Location, LspRange, to_location
from ..._ty_lsp import TyLSP
from .._common import RAW_OBJECTS, HierarchyItem, RawItem


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


def callees_in_response(
    caller: RawItem, outgoing: object
) -> list[tuple[Callee, RawItem]]:
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


def request_callees(
    lsp: TyLSP, callers: list[RawItem]
) -> list[list[tuple[Callee, RawItem]]]:
    """The direct callees of each caller, in the same order. Sends one batch.

    Raises what ``capture`` turns into an ``Error``.
    """
    responses = lsp._request_many(
        "callHierarchy/outgoingCalls", [{"item": caller} for caller in callers]
    )
    return [
        callees_in_response(caller, r)
        for caller, r in zip(callers, responses, strict=True)
    ]
