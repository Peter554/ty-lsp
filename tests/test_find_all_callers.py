"""End-to-end tests of ``find_all_callers`` against ``tests/fixture_project``."""

from py_call_linter import (
    CallerQuery,
    Location,
    TyLSP,
    find_all_callers,
    find_direct_callers,
)

from ._support import PROJECT, find

GRAPH = PROJECT / "shop" / "graph.py"


def defined(name: str) -> Location:
    """Where function ``name`` is defined in ``graph.py`` (the position of its name)."""
    where = find(GRAPH, f"def {name}(")
    return where.model_copy(update={"column": where.column + len("def ")})


def edges(lsp: TyLSP, name: str, **kwargs: int) -> list[tuple[Location, Location]]:
    """The (caller, callee) pairs from ``find_all_callers`` on ``name``."""
    query = CallerQuery(**defined(name).model_dump())
    result = find_all_callers(lsp, query, **kwargs)
    assert isinstance(result, tuple), result
    return [(c.location, c.callee) for c in result]


def test_chain_and_diamond_are_followed_to_the_top(lsp: TyLSP) -> None:
    assert edges(lsp, "leaf") == [
        (defined("mid_a"), defined("leaf")),
        (defined("mid_b"), defined("leaf")),
        # top is reached through both mid_a and mid_b: two edges, but expanded once.
        (defined("top"), defined("mid_a")),
        (defined("top"), defined("mid_b")),
    ]


def test_max_depth_limits_the_levels_followed(lsp: TyLSP) -> None:
    assert edges(lsp, "leaf", max_depth=1) == [
        (defined("mid_a"), defined("leaf")),
        (defined("mid_b"), defined("leaf")),
    ]
    assert len(edges(lsp, "leaf", max_depth=2)) == 4
    assert edges(lsp, "leaf", max_depth=0) == []


def test_depth_one_matches_find_direct_callers(lsp: TyLSP) -> None:
    query = CallerQuery(**defined("leaf").model_dump())
    assert find_all_callers(lsp, query, max_depth=1) == find_direct_callers(lsp, query)


def test_mutual_recursion_terminates(lsp: TyLSP) -> None:
    assert sorted(edges(lsp, "ping"), key=lambda e: e[0].line) == [
        (defined("ping"), defined("pong")),
        (defined("pong"), defined("ping")),
        (defined("start"), defined("ping")),
    ]


def test_self_recursion_terminates(lsp: TyLSP) -> None:
    assert edges(lsp, "countdown") == [(defined("countdown"), defined("countdown"))]


def test_no_callers(lsp: TyLSP) -> None:
    assert edges(lsp, "top") == []


def test_query_from_a_usage(lsp: TyLSP) -> None:
    usage = find(GRAPH, "leaf()", nth=2)
    result = find_all_callers(lsp, CallerQuery(**usage.model_dump()))
    assert isinstance(result, tuple), result
    assert len(result) == 4
