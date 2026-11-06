"""Helpers shared by all the queries."""

from collections.abc import Callable, Iterable
from typing import Any

import pydantic

from .._common import (
    Error,
    Location,
    LspLocation,
    LspRange,
    PathError,
    Result,
    check_file,
    to_location,
)
from .._lsp import ResponseError
from .._ty_lsp import TyLSP


def capture[**P, T](fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> Result[T]:
    """Call ``fn``, turning a failed lookup into an ``Error``.

    A ``PathError`` (the file does not exist), a ``ResponseError`` (the server
    rejected the request) or a ``pydantic.ValidationError`` (it answered with
    something unexpected) becomes an ``Error``. Anything else, such as a crashed server, propagates.
    """
    try:
        return fn(*args, **kwargs)
    except (PathError, ResponseError, pydantic.ValidationError) as exc:
        return Error(str(exc), exc)


def position_params(location: Location) -> dict[str, Any]:
    """The ``TextDocumentPositionParams`` of a 1-based ``Location``.

    Raises ``PathError`` if the file does not exist.
    """
    check_file(location.path)
    return {
        "textDocument": {"uri": location.path.resolve().as_uri()},
        "position": {"line": location.line - 1, "character": location.column - 1},
    }


# Locations


class LspLocationLink(pydantic.BaseModel):
    target_uri: str = pydantic.Field(alias="targetUri")
    target_selection_range: LspRange = pydantic.Field(alias="targetSelectionRange")


_LOCATIONS = pydantic.TypeAdapter(list[LspLocation | LspLocationLink])


def _to_location(location: LspLocation | LspLocationLink) -> Location:
    """Convert an LSP ``Location`` or ``LocationLink`` to a 1-based ``Location``."""
    if isinstance(location, LspLocation):
        return to_location(location.uri, location.range.start)
    return to_location(location.target_uri, location.target_selection_range.start)


def request_locations(lsp: TyLSP, method: str, query: Location) -> tuple[Location, ...]:
    """The locations the server gives for ``method`` (e.g. ``textDocument/definition``) at ``query``.

    Raises what ``capture`` turns into an ``Error``.
    """
    result: Any = lsp._request(method, position_params(query))
    if result is None:
        return ()
    locations = [result] if isinstance(result, dict) else result
    return tuple(_to_location(loc) for loc in _LOCATIONS.validate_python(locations))


# Call and type hierarchies

type RawItem = dict[str, Any]
"""A hierarchy item exactly as the server sent it (it must be sent back as is)."""

RAW_OBJECTS = pydantic.TypeAdapter(list[dict[str, Any]])
"""Validates a response that is a list of JSON objects (``None`` is not accepted)."""


class HierarchyItem(pydantic.BaseModel):
    """The fields of a call or type hierarchy item that we read."""

    name: str
    uri: str
    selection_range: LspRange = pydantic.Field(alias="selectionRange")

    @property
    def location(self) -> Location:
        """Where the item's name is defined."""
        return to_location(self.uri, self.selection_range.start)


def item_location(item: RawItem) -> Location:
    """Where the item's name is defined."""
    return HierarchyItem.model_validate(item).location


def prepare_hierarchy(lsp: TyLSP, method: str, query: Location) -> list[RawItem]:
    """Resolve ``query`` to hierarchy items with ``method``.

    ``method`` is ``textDocument/prepareCallHierarchy`` or
    ``textDocument/prepareTypeHierarchy``. The result is empty if there is nothing
    to resolve, and has several items if the name has several definitions.

    Raises what ``capture`` turns into an ``Error``.
    """
    items: Any = lsp._request(method, position_params(query))
    return RAW_OBJECTS.validate_python(items or [])


def walk_breadth_first[E](
    start: list[RawItem],
    expand: Callable[[list[RawItem]], Iterable[Iterable[tuple[E, RawItem]]]],
    *,
    max_depth: int | None,
    expand_only: Callable[[Location], bool] = lambda _: True,
) -> list[E]:
    """Collect the edges of a graph reachable from ``start``, level by level.

    ``expand`` takes one level of items and returns, for each item (in order), its
    edges, each paired with the item it leads to. Each item is expanded at most
    once, so cycles terminate, but every edge is returned, including those to items
    already seen. ``max_depth`` limits the number of levels (``None`` for all), and
    ``expand_only`` can stop items at some locations from being expanded. The
    ``start`` items are always expanded.
    """
    seen = {item_location(item) for item in start}
    edges: list[E] = []
    frontier = start
    depth = 0
    while frontier and (max_depth is None or depth < max_depth):
        depth += 1
        next_frontier: list[RawItem] = []
        for found in expand(frontier):
            for edge, item in found:
                edges.append(edge)
                location = item_location(item)
                if location not in seen:
                    seen.add(location)
                    if expand_only(location):
                        next_frontier.append(item)
        frontier = next_frontier
    return edges
