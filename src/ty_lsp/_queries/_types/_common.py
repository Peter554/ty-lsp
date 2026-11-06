"""Type hierarchy walk shared by the subtypes and supertypes queries."""

import dataclasses
from typing import Literal

from ..._common import Location
from ..._ty_lsp import TyLSP
from .._common import (
    RAW_OBJECTS,
    HierarchyItem,
    RawItem,
    item_location,
    prepare_hierarchy,
    walk_breadth_first,
)

type Direction = Literal["subtypes", "supertypes"]


@dataclasses.dataclass(frozen=True)
class Edge:
    """``name`` at ``location`` is a direct subtype or supertype of ``origin``."""

    name: str
    location: Location
    origin: Location


def walk_hierarchy(
    lsp: TyLSP, query: Location, direction: Direction, max_depth: int | None
) -> list[Edge]:
    """The edges from the type at ``query`` out to its subtypes or supertypes.

    Breadth-first, each type expanded once. A type reached by several routes (as
    with multiple inheritance) gets an edge for each route.

    Raises ``ResponseError`` or ``pydantic.ValidationError`` on failure.
    """

    def expand(items: list[RawItem]) -> list[list[tuple[Edge, RawItem]]]:
        responses = lsp._request_many(
            f"typeHierarchy/{direction}", [{"item": item} for item in items]
        )
        return [
            [
                (Edge(parsed.name, parsed.location, item_location(item)), raw)
                for raw in RAW_OBJECTS.validate_python(found or [])
                for parsed in [HierarchyItem.model_validate(raw)]
            ]
            for item, found in zip(items, responses, strict=True)
        ]

    start = prepare_hierarchy(lsp, "textDocument/prepareTypeHierarchy", query)
    return walk_breadth_first(start, expand, max_depth=max_depth)
