"""End-to-end tests of ``find_direct_callers`` against ``tests/fixture_project``."""

from py_call_linter import Caller, CallerQuery, Location, TyLSP, find_direct_callers

from ._support import PROJECT, find

MODELS = PROJECT / "shop" / "models.py"
PRICING = PROJECT / "shop" / "pricing.py"
APP = PROJECT / "shop" / "app.py"


def query_at(location: Location) -> CallerQuery:
    return CallerQuery(path=location.path, line=location.line, column=location.column)


def callers_of(lsp: TyLSP, location: Location) -> tuple[Caller, ...]:
    result = find_direct_callers(lsp, query_at(location))
    assert isinstance(result, tuple), result
    return result


def test_function_called_from_two_functions(lsp: TyLSP) -> None:
    callers = callers_of(lsp, find(MODELS, "make_item"))
    by_name = {caller.name: caller for caller in callers}
    assert set(by_name) == {"main", "report"}
    assert by_name["main"].location == find(APP, "main()")
    assert by_name["main"].call_sites == (find(APP, "make_item(", nth=1),)
    assert by_name["report"].call_sites == (find(APP, "make_item(name)"),)


def test_query_from_a_usage_instead_of_the_definition(lsp: TyLSP) -> None:
    from_def = callers_of(lsp, find(MODELS, "make_item"))
    from_usage = callers_of(lsp, find(APP, "make_item(", nth=1))
    assert {c.name for c in from_usage} == {c.name for c in from_def}


def test_method_callers(lsp: TyLSP) -> None:
    callers = callers_of(lsp, find(MODELS, "label"))
    assert [c.name for c in callers] == ["main"]
    assert callers[0].call_sites == (find(APP, "label()"),)


def test_class_callers_are_constructor_calls(lsp: TyLSP) -> None:
    callers = callers_of(lsp, find(MODELS, "Item"))
    assert [c.name for c in callers] == ["make_item"]
    assert callers[0].location.path == MODELS


def test_callers_found_through_reexport(lsp: TyLSP) -> None:
    callers = callers_of(lsp, find(PRICING, "total"))
    assert [c.name for c in callers] == ["main"]


def test_function_without_callers(lsp: TyLSP) -> None:
    assert callers_of(lsp, find(APP, "def report", nth=1)) == ()


def test_position_that_is_not_a_callable(lsp: TyLSP) -> None:
    assert callers_of(lsp, find(APP, "import shop")) == ()
