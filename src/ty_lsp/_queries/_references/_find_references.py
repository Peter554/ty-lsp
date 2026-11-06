"""Find every reference to a name (calls, imports, annotations, ...) using ty."""

from typing import Any

import pydantic

from ..._common import Location, LspLocation, Result, to_location
from ..._ty_lsp import TyLSP
from .._common import capture, position_params, request_locations

_REFERENCES = pydantic.TypeAdapter(list[LspLocation])


def _find(lsp: TyLSP, query: Location) -> tuple[Location, ...]:
    definitions = request_locations(lsp, "textDocument/definition", query)
    # Import statements only count as references when declarations are included
    # too, so ask for them and then drop the definitions ourselves.
    result: Any = lsp._request(
        "textDocument/references",
        {**position_params(query), "context": {"includeDeclaration": True}},
    )
    references = {
        to_location(loc.uri, loc.range.start)
        for loc in _REFERENCES.validate_python(result or [])
    }
    return tuple(
        sorted(
            references - set(definitions),
            key=lambda loc: (str(loc.path), loc.line, loc.column),
        )
    )


def find_references(lsp: TyLSP, query: Location) -> Result[tuple[Location, ...]]:
    """Return every reference to the name at ``query``, except its definition.

    ``query`` is the position of a definition or of a usage.

    References are any use of the name: calls, other expressions (such as passing
    it as a callback), type annotations and import statements, including imports
    that go through a re-export. They are sorted by path, line and column.

    Strings (such as ``__all__ = ["name"]``), ``getattr`` and ``import *`` are not
    references. Attribute references (``obj.method``) are only found where ty can
    infer the type of ``obj``.
    """
    return capture(_find, lsp, query)
