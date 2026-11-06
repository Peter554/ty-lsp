"""End-to-end tests of ``find_definition`` against ``tests/fixture_project``."""

from ty_lsp import Error, Location, TyLSP, find_definition

from ._support import PROJECT, find

APP = PROJECT / "shop" / "app.py"


def query(line_containing: str, name: str) -> Location:
    """Build a query for ``name`` on the first line of ``APP`` containing the text."""
    for line_number, line in enumerate(APP.read_text().splitlines(), start=1):
        if line_containing in line:
            return Location(path=APP, line=line_number, column=line.index(name) + 1)
    raise AssertionError(f"{line_containing!r} not found in {APP}")


def test_function_imported_from_module(lsp: TyLSP) -> None:
    result = find_definition(lsp, query("item = make_item", "make_item"))
    assert result == (find(PROJECT / "shop" / "models.py", "make_item"),)


def test_method_call_on_inferred_type(lsp: TyLSP) -> None:
    result = find_definition(lsp, query("item.label()", "label"))
    assert result == (find(PROJECT / "shop" / "models.py", "label"),)


def test_name_reexported_through_package(lsp: TyLSP) -> None:
    result = find_definition(lsp, query("shop.total", "total"))
    assert result == (find(PROJECT / "shop" / "pricing.py", "total"),)


def test_builtin_resolves_outside_project(lsp: TyLSP) -> None:
    result = find_definition(lsp, query("len(", "len"))
    assert isinstance(result, tuple)
    assert len(result) == 1
    assert not result[0].path.is_relative_to(PROJECT)


def test_undefined_name_has_no_definition(lsp: TyLSP) -> None:
    assert find_definition(lsp, query("undefined_name()", "undefined_name")) == ()


def test_position_outside_file_is_not_a_crash(lsp: TyLSP) -> None:
    result = find_definition(lsp, Location(path=APP, line=999, column=1))
    assert result == () or isinstance(result, Error)
