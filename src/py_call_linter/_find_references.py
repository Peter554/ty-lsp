"""Find every reference to a name (calls, imports, annotations, ...) using ty."""

from typing import Any

import pydantic

from ._go_to_definition import DefinitionQuery, go_to_definition
from ._lsp import ResponseError
from ._ty_lsp import TyLSP
from ._utils import Error, Location, LspLocation, Result, to_location

_LOCATIONS = pydantic.TypeAdapter(list[LspLocation])


class ReferenceQuery(Location):
    """The position of a name (a definition or a usage) whose references to find."""


def find_references(lsp: TyLSP, query: ReferenceQuery) -> Result[tuple[Location, ...]]:
    """Return every reference to the name at ``query``, except its definition.

    References are any use of the name: calls, other expressions (such as passing
    it as a callback), type annotations and import statements, including imports
    that go through a re-export. They are sorted by path, line and column.

    Strings (such as ``__all__ = ["name"]``), ``getattr`` and ``import *`` are not
    references. Attribute references (``obj.method``) are only found where ty can
    infer the type of ``obj``.

    Per-query failures are returned as ``Error``; a crashed server raises
    ``RuntimeError``.
    """
    definitions = go_to_definition(lsp, DefinitionQuery(**query.model_dump()))
    if isinstance(definitions, Error):
        return definitions
    try:
        # Import statements only count as references when declarations are included
        # too, so ask for them and then drop the definitions ourselves.
        result: Any = lsp.request(
            "textDocument/references",
            {
                "textDocument": {"uri": query.path.resolve().as_uri()},
                "position": {"line": query.line - 1, "character": query.column - 1},
                "context": {"includeDeclaration": True},
            },
        )
        references = {
            to_location(loc.uri, loc.range.start)
            for loc in _LOCATIONS.validate_python(result or [])
        }
    except (ResponseError, pydantic.ValidationError) as exc:
        return Error(str(exc), exc)
    return tuple(
        sorted(
            references - set(definitions),
            key=lambda loc: (str(loc.path), loc.line, loc.column),
        )
    )
