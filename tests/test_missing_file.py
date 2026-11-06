"""Every query returns an ``Error`` for a path that is not an existing file."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ty_lsp import (
    Error,
    Location,
    SymbolQuery,
    TyLSP,
    find_all_callees,
    find_all_callers,
    find_all_subtypes,
    find_all_supertypes,
    find_definition,
    find_direct_callees,
    find_direct_callers,
    find_direct_subtypes,
    find_direct_supertypes,
    find_references,
    find_symbol,
    find_type_definition,
    list_symbols,
)

from ._support import PROJECT

AT_LOCATION = [
    find_definition,
    find_type_definition,
    find_references,
    find_direct_callers,
    find_all_callers,
    find_direct_callees,
    find_all_callees,
    find_direct_subtypes,
    find_all_subtypes,
    find_direct_supertypes,
    find_all_supertypes,
]


@pytest.mark.parametrize("query", AT_LOCATION, ids=lambda f: f.__name__)
def test_missing_file_is_an_error(lsp: TyLSP, query: Callable[..., Any]) -> None:
    path = PROJECT / "shop" / "nope.py"
    result = query(lsp, Location(path=path, line=1, column=1))
    assert isinstance(result, Error)
    assert result.message == f"file not found: {path}"


@pytest.mark.parametrize("query", AT_LOCATION, ids=lambda f: f.__name__)
def test_directory_is_an_error(lsp: TyLSP, query: Callable[..., Any]) -> None:
    path = PROJECT / "shop"
    result = query(lsp, Location(path=path, line=1, column=1))
    assert isinstance(result, Error)
    assert result.message == f"not a file: {path}"


def test_symbol_queries_check_the_file(lsp: TyLSP) -> None:
    path = (PROJECT / "shop" / "nope.py").resolve()
    for result in (
        list_symbols(lsp, path),
        find_symbol(lsp, SymbolQuery(path=path, name="x")),
    ):
        assert isinstance(result, Error)
        assert result.message == f"file not found: {path}"
    assert isinstance(list_symbols(lsp, Path(PROJECT)), Error)
