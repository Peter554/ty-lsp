"""Resolve Python names to their definitions using ty."""

from ..._common import Location, Result
from ..._ty_lsp import TyLSP
from .._common import capture, request_locations


def find_definition(lsp: TyLSP, query: Location) -> Result[tuple[Location, ...]]:
    """Return the definition(s) of the name at ``query``.

    There can be several (such as a name defined in branches), and the result is
    empty if the name cannot be resolved.
    """
    return capture(request_locations, lsp, "textDocument/definition", query)
