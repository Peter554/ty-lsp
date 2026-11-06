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
    position_params,
    prepare_hierarchy,
    request_locations,
    walk_breadth_first,
)

_PREPARE = "textDocument/prepareTypeHierarchy"

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

    Raises what ``capture`` turns into an ``Error``.
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

    start = prepare_hierarchy(lsp, _PREPARE, query)
    return walk_breadth_first(start, expand, max_depth=max_depth)


def _in_project(lsp: TyLSP, location: Location) -> bool:
    """Whether the location is in the project's own code, not an installed package."""
    path = location.path
    return path.is_relative_to(lsp._root) and "site-packages" not in path.parts


def walk_subtypes(lsp: TyLSP, query: Location, max_depth: int | None) -> list[Edge]:
    """The edges from the class at ``query`` out to its subclasses in the project.

    Only subclasses defined in the project are found, not those in the standard
    library or installed packages. One ``textDocument/implementation`` request gives
    all of them at once, and ``typeHierarchy/supertypes`` gives the edges between
    them. (ty's ``typeHierarchy/subtypes`` would search the whole project for each
    class, which takes about a second per class.)

    Breadth-first, each class expanded once. A class reached by several routes (as
    with multiple inheritance) gets an edge for each route.

    Raises ``ResponseError`` or ``pydantic.ValidationError`` on failure.
    """
    roots = prepare_hierarchy(lsp, _PREPARE, query)
    root_locations = {item_location(item) for item in roots}
    # Every subclass, from any of the roots (the roots themselves may be included).
    members: dict[Location, None] = {}
    for root in root_locations:
        for location in request_locations(lsp, "textDocument/implementation", root):
            if location not in root_locations and _in_project(lsp, location):
                members[location] = None

    # The subclasses as type hierarchy items, keyed by where their names are.
    items: dict[Location, RawItem] = {item_location(item): item for item in roots}
    responses = lsp._request_many(
        _PREPARE, [position_params(location) for location in members]
    )
    for response in responses:
        for item in RAW_OBJECTS.validate_python(response or []):
            items.setdefault(item_location(item), item)

    # A subclass's direct supertypes that are in the set give the edges.
    children: dict[Location, list[tuple[Edge, RawItem]]] = {}
    subclasses = [
        item for location, item in items.items() if location not in root_locations
    ]
    supertypes = lsp._request_many(
        "typeHierarchy/supertypes", [{"item": item} for item in subclasses]
    )
    for item, found in zip(subclasses, supertypes, strict=True):
        parsed = HierarchyItem.model_validate(item)
        for parent in RAW_OBJECTS.validate_python(found or []):
            parent_location = item_location(parent)
            if parent_location in items:
                edge = Edge(parsed.name, parsed.location, parent_location)
                children.setdefault(parent_location, []).append((edge, item))
    for edges in children.values():
        edges.sort(
            key=lambda e: (
                str(e[0].location.path),
                e[0].location.line,
                e[0].location.column,
            )
        )

    def expand(frontier: list[RawItem]) -> list[list[tuple[Edge, RawItem]]]:
        return [children.get(item_location(item), []) for item in frontier]

    return walk_breadth_first(roots, expand, max_depth=max_depth)
