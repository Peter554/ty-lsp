"""Find the implementations of a class or method using ty."""

from ..._common import Location, Result
from ..._ty_lsp import TyLSP
from .._common import capture, request_locations


def find_implementations(lsp: TyLSP, query: Location) -> Result[tuple[Location, ...]]:
    """Return the implementations of the class or method at ``query``, as ty gives them.

    For a class these are its subclasses, and for a method the methods that override
    it, at any depth. This is ty's "go to implementation" (``textDocument/implementation``)
    unchanged: the result can include the class or method itself, and classes that
    only match a ``Protocol`` structurally (without inheriting from it) are not found.
    """
    return capture(request_locations, lsp, "textDocument/implementation", query)
