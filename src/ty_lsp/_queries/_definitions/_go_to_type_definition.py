"""Resolve Python names to the definitions of their types using ty."""

from ..._common import Location, Result
from ..._ty_lsp import TyLSP
from .._common import capture, request_locations


def go_to_type_definition(lsp: TyLSP, query: Location) -> Result[tuple[Location, ...]]:
    """Return where the type of the name at ``query`` is defined.

    For a variable, parameter or attribute this is the class of its inferred
    type, not where the variable itself is defined (use ``go_to_definition`` for
    that). The result is empty if there is no such class.
    """
    return capture(request_locations, lsp, "textDocument/typeDefinition", query)
