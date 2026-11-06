"""End-to-end tests of ``find_direct_callers`` against ``tests/fixture_project``."""

from collections import Counter
from typing import Any, cast

from py_call_linter import (
    Caller,
    CallerQuery,
    Location,
    TyLSP,
    find_direct_callers,
    find_direct_callers_many,
)

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


class _CountingLSP:
    """Wraps a ``TyLSP`` and counts the requests sent, by method."""

    def __init__(self, inner: TyLSP) -> None:
        self.inner = inner
        self.counts: Counter[str] = Counter()

    def request(self, method: str, params: Any) -> Any:
        self.counts[method] += 1
        return self.inner.request(method, params)

    def request_many(self, method: str, params_list: Any, *, window: int = 16) -> Any:
        self.counts[method] += len(params_list)
        return self.inner.request_many(method, params_list, window=window)


def test_many_queries_are_the_same_as_joining_the_single_results(lsp: TyLSP) -> None:
    make_item = query_at(find(MODELS, "make_item"))
    label = query_at(find(MODELS, "label"))
    singles = [find_direct_callers(lsp, q) for q in (make_item, label)]
    assert all(isinstance(r, tuple) for r in singles)
    expected = tuple(c for r in singles if isinstance(r, tuple) for c in r)
    assert find_direct_callers_many(lsp, [make_item, label]) == expected


def test_a_definition_given_several_times_is_looked_up_once(lsp: TyLSP) -> None:
    make_item = query_at(find(MODELS, "make_item"))
    counting = _CountingLSP(lsp)
    result = find_direct_callers_many(cast("TyLSP", counting), [make_item] * 3)
    assert result == find_direct_callers(lsp, make_item)
    assert counting.counts["callHierarchy/incomingCalls"] == 1


def test_no_queries(lsp: TyLSP) -> None:
    assert find_direct_callers_many(lsp, []) == ()
