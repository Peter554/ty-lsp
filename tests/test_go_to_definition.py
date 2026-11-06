"""End-to-end tests of ``go_to_definition`` against ``tests/fixture_project``."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from py_call_linter import DefinitionQuery, Error, Location, TyLSP, go_to_definition

PROJECT = Path(__file__).parent / "fixture_project"
APP = PROJECT / "shop" / "app.py"


@pytest.fixture(scope="module")
def lsp() -> Iterator[TyLSP]:
    with TyLSP(PROJECT) as lsp:
        yield lsp


def query(line_containing: str, name: str) -> DefinitionQuery:
    """Build a query for ``name`` on the first line of ``APP`` containing the text."""
    for line_number, line in enumerate(APP.read_text().splitlines(), start=1):
        if line_containing in line:
            return DefinitionQuery(
                path=APP, line=line_number, column=line.index(name) + 1
            )
    raise AssertionError(f"{line_containing!r} not found in {APP}")


def find(path: Path, text: str) -> Location:
    """The location of ``text`` (1-based) in the first line of ``path`` containing it."""
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if text in line:
            return Location(
                path=path.resolve(), line=line_number, column=line.index(text) + 1
            )
    raise AssertionError(f"{text!r} not found in {path}")


def test_function_imported_from_module(lsp: TyLSP) -> None:
    result = go_to_definition(lsp, query("item = make_item", "make_item"))
    assert result == (find(PROJECT / "shop" / "models.py", "make_item"),)


def test_method_call_on_inferred_type(lsp: TyLSP) -> None:
    result = go_to_definition(lsp, query("item.label()", "label"))
    assert result == (find(PROJECT / "shop" / "models.py", "label"),)


def test_name_reexported_through_package(lsp: TyLSP) -> None:
    result = go_to_definition(lsp, query("shop.total", "total"))
    assert result == (find(PROJECT / "shop" / "pricing.py", "total"),)


def test_builtin_resolves_outside_project(lsp: TyLSP) -> None:
    result = go_to_definition(lsp, query("len(", "len"))
    assert isinstance(result, tuple)
    assert len(result) == 1
    assert not result[0].path.is_relative_to(PROJECT)


def test_undefined_name_has_no_definition(lsp: TyLSP) -> None:
    assert go_to_definition(lsp, query("undefined_name()", "undefined_name")) == ()


def test_position_outside_file_is_not_a_crash(lsp: TyLSP) -> None:
    result = go_to_definition(lsp, DefinitionQuery(path=APP, line=999, column=1))
    assert result == () or isinstance(result, Error)
