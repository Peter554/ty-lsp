"""Tests of sending several LSP requests at once with ``TyLSP.request_many``."""

import pytest

from py_call_linter import TyLSP
from py_call_linter._lsp import ResponseError

from ._support import PROJECT, name_in

APP = PROJECT / "shop" / "app.py"


def definition_params() -> list[dict[str, object]]:
    """``textDocument/definition`` requests for a handful of names in app.py."""
    names = ["make_item", "label", "total", "main", "report"]
    locations = [name_in(APP, name, name) for name in names]
    return [
        {
            "textDocument": {"uri": loc.path.as_uri()},
            "position": {"line": loc.line - 1, "character": loc.column - 1},
        }
        for loc in locations
    ]


def test_results_match_sending_the_requests_one_at_a_time(lsp: TyLSP) -> None:
    params = definition_params()
    one_at_a_time = [lsp.request("textDocument/definition", p) for p in params]
    assert lsp.request_many("textDocument/definition", params) == one_at_a_time
    assert any(result for result in one_at_a_time)


@pytest.mark.parametrize("window", [1, 2, 64])
def test_any_window_size_gives_the_same_results(lsp: TyLSP, window: int) -> None:
    params = definition_params() * 8  # more requests than the smaller windows
    expected = [lsp.request("textDocument/definition", p) for p in params]
    assert (
        lsp.request_many("textDocument/definition", params, window=window) == expected
    )


def test_no_requests(lsp: TyLSP) -> None:
    assert lsp.request_many("textDocument/definition", []) == []


def test_a_failing_request_raises_and_the_connection_stays_usable(lsp: TyLSP) -> None:
    with pytest.raises(ResponseError):
        lsp.request_many("textDocument/notARealMethod", [{}, {}, {}])
    # The failed responses were all consumed, so the next request is answered correctly.
    params = definition_params()
    assert lsp.request_many("textDocument/definition", params) == [
        lsp.request("textDocument/definition", p) for p in params
    ]
