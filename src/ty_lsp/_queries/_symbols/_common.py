"""Document symbol request shared by the symbol queries."""

from pathlib import Path
from typing import Any

import pydantic

from ..._common import LspRange
from ..._ty_lsp import TyLSP


class DocumentSymbol(pydantic.BaseModel):
    name: str
    range: LspRange
    selection_range: LspRange = pydantic.Field(alias="selectionRange")
    children: list["DocumentSymbol"] | None = None


_SYMBOLS = pydantic.TypeAdapter(list[DocumentSymbol])


def request_symbols(lsp: TyLSP, path: Path) -> list[DocumentSymbol]:
    """The symbols of the file at the resolved ``path``, nested ones as children.

    Raises ``ResponseError`` or ``pydantic.ValidationError`` on failure.
    """
    result: Any = lsp._request(
        "textDocument/documentSymbol", {"textDocument": {"uri": path.as_uri()}}
    )
    return _SYMBOLS.validate_python(result or [])
