"""Find and list the symbols defined in a file, using ty."""

from pathlib import Path
from typing import Any

import pydantic

from ._lsp import ResponseError
from ._ty_lsp import TyLSP
from ._utils import Error, Frozen, Location, LspRange, Result, to_location


class SymbolQuery(Frozen):
    """A symbol named by file and name, e.g. ``foo`` or ``Class.method``."""

    path: Path
    name: str
    """A name defined in the file. Use dots to reach nested symbols (``A.b``)."""


class Symbol(Frozen):
    """A function, class, method or variable defined in a file."""

    name: str
    location: Location
    """Where the symbol's name is."""
    start: Location
    """Where the whole definition starts: its first decorator, if it has any."""


class _DocumentSymbol(pydantic.BaseModel):
    name: str
    range: LspRange
    selection_range: LspRange = pydantic.Field(alias="selectionRange")
    children: list["_DocumentSymbol"] | None = None


_SYMBOLS = pydantic.TypeAdapter(list[_DocumentSymbol])


def _document_symbols(path: Path, result: Any) -> list[_DocumentSymbol]:
    return _SYMBOLS.validate_python(result or [])


def _request_symbols(lsp: TyLSP, path: Path) -> Result[list[_DocumentSymbol]]:
    try:
        result: Any = lsp.request(
            "textDocument/documentSymbol", {"textDocument": {"uri": path.as_uri()}}
        )
        return _document_symbols(path, result)
    except (ResponseError, pydantic.ValidationError) as exc:
        return Error(str(exc), exc)


def list_symbols(lsp: TyLSP, path: Path) -> Result[tuple[Symbol, ...]]:
    """Return every symbol defined in ``path``, nested ones included.

    Symbols come in file order, with a symbol before the ones nested inside it.
    Per-file failures are returned as ``Error``; a crashed server raises
    ``RuntimeError``.
    """
    path = path.resolve()
    symbols = _request_symbols(lsp, path)
    if isinstance(symbols, Error):
        return symbols
    uri = path.as_uri()
    flat: list[Symbol] = []

    def visit(nodes: list[_DocumentSymbol]) -> None:
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


def find_symbol(lsp: TyLSP, query: SymbolQuery) -> Result[tuple[Location, ...]]:
    """Return where the symbol ``query.name`` is defined in ``query.path``.

    Functions, classes, methods and variables defined in the file are found; a
    dotted name looks inside the earlier names (``Class.method``). The result is
    the position of each definition's name, and is empty if there is none. There
    can be several if the name is defined more than once, such as in branches.

    Per-query failures are returned as ``Error``; a crashed server raises
    ``RuntimeError``.
    """
    path = query.path.resolve()
    symbols = _request_symbols(lsp, path)
    if isinstance(symbols, Error):
        return symbols
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
