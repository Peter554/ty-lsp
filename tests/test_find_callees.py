"""End-to-end tests of ``find_direct_callees`` and ``find_all_callees``."""

from pathlib import Path

from py_call_linter import (
    Callee,
    CalleeQuery,
    Error,
    Location,
    TyLSP,
    find_all_callees,
    find_direct_callees,
)

from ._support import PROJECT, find, name_in

SHOP = PROJECT / "shop"
GRAPH = SHOP / "graph.py"
APP = SHOP / "app.py"
MODELS = SHOP / "models.py"


def defined(name: str) -> Location:
    """Where function ``name`` is defined in ``graph.py`` (the position of its name)."""
    return name_in(GRAPH, f"def {name}(", name)


def query(location: Location) -> CalleeQuery:
    return CalleeQuery(**location.model_dump())


def direct(lsp: TyLSP, name: str) -> tuple[Callee, ...]:
    result = find_direct_callees(lsp, query(defined(name)))
    assert isinstance(result, tuple), result
    return result


def all_edges(
    lsp: TyLSP,
    name: str,
    *,
    max_depth: int | None = None,
    within: Path | None = None,
) -> list[tuple[Location, Location]]:
    """(caller, callee) pairs from ``find_all_callees``."""
    result = find_all_callees(
        lsp, query(defined(name)), max_depth=max_depth, within=within
    )
    assert isinstance(result, tuple), result
    return [(c.caller, c.location) for c in result]


def test_direct_callees_and_their_call_sites(lsp: TyLSP) -> None:
    callees = direct(lsp, "top")
    assert [(c.name, c.location, c.caller) for c in callees] == [
        ("mid_a", defined("mid_a"), defined("top")),
        ("mid_b", defined("mid_b"), defined("top")),
    ]
    assert callees[0].call_sites == (name_in(GRAPH, "    mid_a()", "mid_a"),)


def test_only_direct_callees_are_returned(lsp: TyLSP) -> None:
    assert [c.location for c in direct(lsp, "mid_a")] == [defined("leaf")]


def test_function_that_calls_nothing(lsp: TyLSP) -> None:
    assert direct(lsp, "leaf") == ()


def test_callee_called_twice_is_one_entry_with_both_call_sites(lsp: TyLSP) -> None:
    (callee,) = direct(lsp, "twice")
    assert callee.location == defined("helper")
    assert [site.line for site in callee.call_sites] == [
        find(GRAPH, "    helper()", nth=1).line,
        find(GRAPH, "    helper()", nth=2).line,
    ]


def test_callees_outside_the_project_are_included(lsp: TyLSP) -> None:
    result = find_direct_callees(lsp, query(name_in(APP, "def main", "main")))
    assert isinstance(result, tuple), result
    names = {c.name for c in result}
    assert {"make_item", "label", "total"} <= names
    assert "print" in names  # a builtin
    builtin = next(c for c in result if c.name == "print")
    assert not builtin.location.path.is_relative_to(PROJECT)
    # The call sites are in the caller's file, not the callee's.
    assert all(site.path == APP for site in builtin.call_sites)


def test_query_from_a_usage_instead_of_the_definition(lsp: TyLSP) -> None:
    usage = name_in(GRAPH, "    mid_a()", "mid_a")  # a call inside top
    assert find_direct_callees(lsp, query(usage)) == direct(lsp, "mid_a")


def test_callee_that_is_a_class_is_a_constructor_call(lsp: TyLSP) -> None:
    result = find_direct_callees(
        lsp, query(name_in(MODELS, "def make_item", "make_item"))
    )
    assert isinstance(result, tuple), result
    assert [c.name for c in result] == ["Item"]


def test_all_callees_follow_chains_and_diamonds(lsp: TyLSP) -> None:
    assert all_edges(lsp, "top", within=SHOP) == [
        (defined("top"), defined("mid_a")),
        (defined("top"), defined("mid_b")),
        # leaf is reached through both, but it is expanded once.
        (defined("mid_a"), defined("leaf")),
        (defined("mid_b"), defined("leaf")),
    ]


def test_max_depth_limits_the_levels_followed(lsp: TyLSP) -> None:
    assert all_edges(lsp, "top", max_depth=1) == [
        (defined("top"), defined("mid_a")),
        (defined("top"), defined("mid_b")),
    ]
    assert len(all_edges(lsp, "top", max_depth=2)) == 4
    assert all_edges(lsp, "top", max_depth=0) == []


def test_depth_one_matches_find_direct_callees(lsp: TyLSP) -> None:
    q = query(defined("top"))
    assert find_all_callees(lsp, q, max_depth=1) == find_direct_callees(lsp, q)


def test_mutual_recursion_terminates(lsp: TyLSP) -> None:
    assert all_edges(lsp, "start") == [
        (defined("start"), defined("ping")),
        (defined("ping"), defined("pong")),
        (defined("pong"), defined("ping")),
    ]


def test_self_recursion_terminates(lsp: TyLSP) -> None:
    assert all_edges(lsp, "countdown") == [(defined("countdown"), defined("countdown"))]


def test_within_stops_expanding_callees_outside_the_directory(lsp: TyLSP) -> None:
    main = query(name_in(APP, "def main", "main"))

    def callers_of_edges(within: Path) -> set[Location]:
        result = find_all_callees(lsp, main, within=within)
        assert isinstance(result, tuple), result
        return {edge.caller for edge in result}

    # Inside shop, main's callee make_item is expanded (it calls Item); outside it
    # is returned but not expanded.
    make_item = name_in(MODELS, "def make_item", "make_item")
    assert make_item in callers_of_edges(SHOP)
    assert make_item not in callers_of_edges(SHOP / "ledger")


def test_function_without_a_call_hierarchy_item(lsp: TyLSP) -> None:
    variable = name_in(SHOP / "markers.py", "alias_marker =", "alias_marker")
    assert find_direct_callees(lsp, query(variable)) == ()
    assert not isinstance(find_all_callees(lsp, query(variable)), Error)
