"""List the symbols defined in a file, using ty."""

from pathlib import Path

from ..._common import Frozen, Location, Result, to_location
from ..._ty_lsp import TyLSP
from .._common import capture
from ._common import DocumentSymbol, request_symbols


class Symbol(Frozen):
    """A function, class, method or variable defined in a file."""

    name: str
    location: Location
    """Where the symbol's name is."""
    start: Location
    """Where the whole definition starts: its first decorator, if it has any."""


def _list(lsp: TyLSP, path: Path) -> tuple[Symbol, ...]:
    path = path.resolve()
    symbols = request_symbols(lsp, path)
    uri = path.as_uri()
    flat: list[Symbol] = []

    def visit(nodes: list[DocumentSymbol]) -> None:
        for node in nodes:
            flat.append(
                Symbol(
                    name=node.name,
                    location=to_location(uri, node.selection_range.start),
                    start=to_location(uri, node.range.start),
                )
            )
            visit(node.children or [])

    visit(symbols)
    return tuple(flat)


def list_symbols(lsp: TyLSP, path: Path) -> Result[tuple[Symbol, ...]]:
    """Return every symbol defined in ``path``, nested ones included.

    Symbols come in file order, with a symbol before the ones nested inside it.
    """
    return capture(_list, lsp, path)
