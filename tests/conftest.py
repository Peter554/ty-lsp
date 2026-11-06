from collections.abc import Iterator

import pytest

from py_call_linter import TyLSP

from ._support import PROJECT


@pytest.fixture(scope="module")
def lsp() -> Iterator[TyLSP]:
    with TyLSP(PROJECT) as lsp:
        yield lsp
