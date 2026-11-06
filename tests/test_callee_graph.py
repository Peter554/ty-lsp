"""End-to-end tests of ``build_callee_graph`` against ``tests/fixture_project``."""

from pathlib import Path

from py_call_linter import (
    CalleeGraph,
    CalleeQuery,
    Location,
    TyLSP,
    build_callee_graph,
    find_all_callees,
    find_direct_callees,
)

from ._support import PROJECT, name_in

SHOP = PROJECT / "shop"
GRAPH = SHOP / "graph.py"
APP = SHOP / "app.py"
MODELS = SHOP / "models.py"


def defined(name: str) -> Location:
    return name_in(GRAPH, f"def {name}(", name)


def build(
    lsp: TyLSP, starts: list[Location], within: Path | None = SHOP
) -> CalleeGraph:
    graph = build_callee_graph(lsp, starts, within=within)
    assert isinstance(graph, CalleeGraph), graph
    return graph


def test_every_reachable_function_is_looked_up_once(lsp: TyLSP) -> None:
    graph = build(lsp, [defined("top")])
    assert set(graph.edges) == {
        defined("top"),
        defined("mid_a"),
        defined("mid_b"),
        defined("leaf"),
    }
    assert graph.callees_of(defined("leaf")) == ()


def test_direct_callees_match_find_direct_callees(lsp: TyLSP) -> None:
    graph = build(lsp, [defined("top"), defined("ping")])
    for name in ("top", "ping"):
        direct = find_direct_callees(lsp, CalleeQuery(**defined(name).model_dump()))
        assert graph.callees_of(defined(name)) == direct


def test_reachable_from_matches_find_all_callees_for_every_start(lsp: TyLSP) -> None:
    names = ["top", "mid_a", "start", "ping", "countdown", "twice", "leaf"]
    graph = build(lsp, [defined(n) for n in names])
    for name in names:
        query = CalleeQuery(**defined(name).model_dump())
        assert graph.reachable_from(defined(name)) == find_all_callees(
            lsp, query, within=SHOP
        ), name


def test_starts_that_share_callees_share_the_lookup(lsp: TyLSP) -> None:
    graph = build(lsp, [defined("mid_a"), defined("mid_b")])
    assert graph.reachable_from(defined("mid_a"))[0].location == defined("leaf")
    assert graph.reachable_from(defined("mid_b"))[0].location == defined("leaf")
    assert list(graph.edges).count(defined("leaf")) == 1


def test_max_depth_limits_the_levels_followed(lsp: TyLSP) -> None:
    graph = build(lsp, [defined("top")])
    assert len(graph.reachable_from(defined("top"), max_depth=1)) == 2
    assert len(graph.reachable_from(defined("top"), max_depth=2)) == 4
    assert graph.reachable_from(defined("top"), max_depth=0) == ()


def test_recursion_terminates(lsp: TyLSP) -> None:
    graph = build(lsp, [defined("start")])
    reached = [(c.caller, c.location) for c in graph.reachable_from(defined("start"))]
    assert reached == [
        (defined("start"), defined("ping")),
        (defined("ping"), defined("pong")),
        (defined("pong"), defined("ping")),
    ]


def test_unknown_function_has_no_callees(lsp: TyLSP) -> None:
    graph = build(lsp, [defined("leaf")])
    assert graph.callees_of(defined("top")) == ()
    assert graph.reachable_from(defined("top")) == ()


def test_within_stops_looking_up_callees_outside_the_directory(lsp: TyLSP) -> None:
    main = name_in(APP, "def main", "main")
    make_item = name_in(MODELS, "def make_item", "make_item")
    assert make_item in build(lsp, [main], within=SHOP).edges
    outside = build(lsp, [main], within=SHOP / "ledger")
    assert make_item not in outside.edges
    # It is still a callee of main, just not looked up itself.
    assert make_item in {c.location for c in outside.callees_of(main)}


def test_starts_that_are_not_callable_are_skipped(lsp: TyLSP) -> None:
    variable = name_in(SHOP / "markers.py", "alias_marker =", "alias_marker")
    graph = build(lsp, [variable, defined("leaf")])
    assert set(graph.edges) == {defined("leaf")}


def test_no_starts(lsp: TyLSP) -> None:
    assert build(lsp, []).edges == {}
