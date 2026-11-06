"""End-to-end tests of ``find_symbol`` against ``tests/fixture_project``."""

from pathlib import Path

from ty_lsp import (
    Error,
    Location,
    Result,
    SymbolQuery,
    TyLSP,
    find_symbol,
)

from ._support import PROJECT, name_in

SHOP = PROJECT / "shop"
ENTRIES = SHOP / "ledger" / "entries.py"


def symbol(lsp: TyLSP, path: Path, name: str) -> Result[tuple[Location, ...]]:
    return find_symbol(lsp, SymbolQuery(path=path, name=name))


def test_function(lsp: TyLSP) -> None:
    assert symbol(lsp, ENTRIES, "post") == (name_in(ENTRIES, "def post", "post"),)


def test_decorated_function_points_at_the_name_not_the_decorator(lsp: TyLSP) -> None:
    assert symbol(lsp, ENTRIES, "cached") == (name_in(ENTRIES, "def cached", "cached"),)


def test_non_ascii_name(lsp: TyLSP) -> None:
    assert symbol(lsp, ENTRIES, "café") == (name_in(ENTRIES, "def café", "café"),)


def test_class_and_nested_method(lsp: TyLSP) -> None:
    assert symbol(lsp, ENTRIES, "Ledger") == (
        name_in(ENTRIES, "class Ledger", "Ledger"),
    )
    assert symbol(lsp, ENTRIES, "Ledger.close") == (
        name_in(ENTRIES, "    def close", "close"),
    )


def test_variable(lsp: TyLSP) -> None:
    markers = SHOP / "markers.py"
    assert symbol(lsp, markers, "alias_marker") == (
        name_in(markers, "alias_marker =", "alias_marker"),
    )


def test_nested_names_are_not_top_level(lsp: TyLSP) -> None:
    assert symbol(lsp, ENTRIES, "close") == ()


def test_unknown_name(lsp: TyLSP) -> None:
    assert symbol(lsp, ENTRIES, "nope") == ()
    assert symbol(lsp, ENTRIES, "Ledger.nope") == ()
    assert symbol(lsp, ENTRIES, "post.nope") == ()


def test_missing_file(lsp: TyLSP) -> None:
    result = symbol(lsp, SHOP / "missing.py", "x")
    assert result == () or isinstance(result, Error)
