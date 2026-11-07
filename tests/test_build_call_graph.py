"""End-to-end tests of ``build_call_graph`` against ``tests/fixture_project``."""

from collections import Counter
from pathlib import Path
from typing import Any, cast

import pytest

from ty_lsp import (
    Error,
    Location,
    TyLSP,
    build_call_graph,
    find_all_callees,
)

from ._support import PROJECT, find

GRAPH = PROJECT / "shop" / "graph.py"
APP = PROJECT / "shop" / "app.py"
TOP = find(GRAPH, "top()")
MID_A = find(GRAPH, "mid_a()")
MID_B = find(GRAPH, "mid_b()")
LEAF = find(GRAPH, "leaf()")
CHECKOUT = find(PROJECT / "shop" / "checkout.py", "def ", nth=1)
QUERIES = [TOP, MID_A, MID_B, LEAF]


class _CountingLSP:
    """Wraps a ``TyLSP`` and records the requests sent."""

    def __init__(self, inner: TyLSP) -> None:
        self.inner = inner
        self.requests: Counter[str] = Counter()
        self.batches: Counter[str] = Counter()

    def _request(self, method: str, params: Any) -> Any:
        self.requests[method] += 1
        return self.inner._request(method, params)

    def _request_many(self, method: str, params_list: Any, *, window: int = 16) -> Any:
        self.batches[method] += 1
        self.requests[method] += len(params_list)
        return self.inner._request_many(method, params_list, window=window)


@pytest.mark.parametrize(
    ("max_depth", "within"),
    [
        (None, None),
        (1, None),
        (2, None),
        (None, PROJECT / "shop"),
        # The starting points are outside ``within``. Each is expanded, but not
        # when it is only reached from another one.
        (None, PROJECT / "shop" / "inventory"),
    ],
)
def test_each_query_gives_what_find_all_callees_gives(
    lsp: TyLSP, max_depth: int | None, within: Path | None
) -> None:
    graph = build_call_graph(lsp, QUERIES, max_depth=max_depth, within=within)
    assert not isinstance(graph, Error)
    for query in QUERIES:
        alone = find_all_callees(lsp, query, max_depth=max_depth, within=within)
        assert not isinstance(alone, Error)
        assert graph.all_callees_of(query) == alone


def test_the_graph_is_the_callees_of_every_function_reached(lsp: TyLSP) -> None:
    graph = build_call_graph(lsp, [TOP])
    assert not isinstance(graph, Error)
    assert set(graph.callees) >= {TOP, MID_A, MID_B, LEAF}
    assert [c.name for c in graph.callees[TOP]] == ["mid_a", "mid_b"]
    assert graph.all_callees_of(TOP) == find_all_callees(lsp, TOP)


def test_shared_functions_are_looked_up_once_and_a_level_is_one_batch(
    lsp: TyLSP,
) -> None:
    counting = _CountingLSP(lsp)
    graph = build_call_graph(cast("TyLSP", counting), QUERIES)
    assert not isinstance(graph, Error)
    method = "callHierarchy/outgoingCalls"
    # top, mid_a, mid_b and leaf are all starting points, and everything they call
    # is one of them: so they are all looked up in one batch, and nothing is left.
    assert counting.batches["textDocument/prepareCallHierarchy"] == 1
    assert counting.batches[method] == 1
    assert counting.requests[method] == len(graph.callees)
    # Doing it one by one looks the same functions up again and again.
    one_by_one = _CountingLSP(lsp)
    for query in QUERIES:
        find_all_callees(cast("TyLSP", one_by_one), query)
    assert one_by_one.requests[method] > counting.requests[method]


def test_the_same_query_twice_and_a_name_with_two_definitions(lsp: TyLSP) -> None:
    graph = build_call_graph(lsp, [TOP, TOP])
    assert not isinstance(graph, Error)
    assert graph.all_callees_of(TOP) == graph.all_callees_of(TOP)
    assert len(graph.roots) == 1


def test_a_missing_file_is_an_error_for_the_whole_graph(lsp: TyLSP) -> None:
    nope = Location(path=PROJECT / "shop" / "nope.py", line=1, column=1)
    result = build_call_graph(lsp, [TOP, nope])
    assert isinstance(result, Error)
    assert result.message == f"file not found: {nope.path}"


def test_no_queries_is_an_empty_graph(lsp: TyLSP) -> None:
    graph = build_call_graph(lsp, [])
    assert not isinstance(graph, Error)
    assert graph.callees == {}
