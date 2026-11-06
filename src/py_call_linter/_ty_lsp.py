"""A long-lived ``ty server`` process."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Self

from ._lsp import LSPClient


class TyLSP:
    """Start once, then send many requests."""

    def __init__(self, root: Path) -> None:
        """Start ``ty server`` (via uvx) for the project at ``root``."""
        self.root = root.resolve()
        self._lsp = LSPClient(["uvx", "ty", "server"], self.root)
        try:
            self._lsp.request(
                "initialize",
                {
                    "processId": None,
                    "rootUri": self.root.as_uri(),
                    "workspaceFolders": [
                        {"uri": self.root.as_uri(), "name": self.root.name}
                    ],
                    "capabilities": {
                        # Nested symbols with the position of each name.
                        "textDocument": {
                            "documentSymbol": {
                                "hierarchicalDocumentSymbolSupport": True
                            }
                        }
                    },
                },
            )
            self._lsp.notify("initialized", {})
        except BaseException:
            self._lsp.close()
            raise

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._lsp.close()

    def request(self, method: str, params: Any) -> Any:
        return self._lsp.request(method, params)

    def request_many(
        self, method: str, params_list: Sequence[Any], *, window: int = 16
    ) -> list[Any]:
        """Send many requests of one method at once; see ``LSPClient.request_many``."""
        return self._lsp.request_many(method, params_list, window=window)
