"""Find where a symbol is defined in a file, using ty."""

from pathlib import Path

from ..._common import Frozen, Location, Result, to_location
from ..._ty_lsp import TyLSP
from .._common import capture
from ._common import request_symbols


class SymbolQuery(Frozen):
    """A symbol named by file and name, e.g. ``foo`` or ``Class.method``."""

    path: Path
    name: str
    """A name defined in the file. Use dots to reach nested symbols (``A.b``)."""


def _find(lsp: TyLSP, query: SymbolQuery) -> tuple[Location, ...]:
    path = query.path.resolve()
    symbols = request_symbols(lsp, path)
    *parents, last = query.name.split(".")
    for parent in parents:
        symbols = [
            child
            for symbol in symbols
            if symbol.name == parent
            for child in symbol.children or []
        ]
    return tuple(
        to_location(path.as_uri(), symbol.selection_range.start)
        for symbol in symbols
        if symbol.name == last
    )


def find_symbol(lsp: TyLSP, query: SymbolQuery) -> Result[tuple[Location, ...]]:
    """Return where the symbol ``query.name`` is defined in ``query.path``.

    Functions, classes, methods and variables defined in the file are found; a
    dotted name looks inside the earlier names (``Class.method``). Names match
    exactly, including case. The result is
    the position of each definition's name, and is empty if there is none. There
    can be several if the name is defined more than once, such as in branches.
    """
    return capture(_find, lsp, query)
