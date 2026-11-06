from collections.abc import Iterator

import pytest

from ty_lsp import TyLSP

from ._support import PROJECT


@pytest.fixture(scope="module")
def lsp() -> Iterator[TyLSP]:
    with TyLSP(PROJECT) as lsp:
        yield lsp
