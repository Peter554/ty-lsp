"""Resolve Python names to their definitions using ty."""

from typing import Any

import pydantic

from ._lsp import ResponseError
from ._ty_lsp import TyLSP
from ._utils import Error, Location, LspRange, Result, to_location


class DefinitionQuery(Location):
    """The position of a name whose definition to look up."""


class _LspLocation(pydantic.BaseModel):
    uri: str
    range: LspRange


class _LspLocationLink(pydantic.BaseModel):
    target_uri: str = pydantic.Field(alias="targetUri")
    target_selection_range: LspRange = pydantic.Field(alias="targetSelectionRange")


_LOCATIONS = pydantic.TypeAdapter(list[_LspLocation | _LspLocationLink])


def _to_location(location: _LspLocation | _LspLocationLink) -> Location:
    """Convert an LSP ``Location`` or ``LocationLink`` to a 1-based ``Location``."""
    if isinstance(location, _LspLocation):
        return to_location(location.uri, location.range.start)
    return to_location(location.target_uri, location.target_selection_range.start)


def go_to_definition(
    lsp: TyLSP, query: DefinitionQuery
) -> Result[tuple[Location, ...]]:
    """Return the definition(s) of the name at ``query``.

    Per-query failures are returned as ``Error``; a crashed server raises
    ``RuntimeError``.
    """
    try:
        result: Any = lsp.request(
            "textDocument/definition",
            {
                "textDocument": {"uri": query.path.resolve().as_uri()},
                "position": {"line": query.line - 1, "character": query.column - 1},
            },
        )
        if result is None:
            return ()
        locations = [result] if isinstance(result, dict) else result
        return tuple(_to_location(loc) for loc in _LOCATIONS.validate_python(locations))
    except (ResponseError, pydantic.ValidationError) as exc:
        return Error(str(exc), exc)
