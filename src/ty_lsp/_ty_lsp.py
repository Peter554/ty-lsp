"""A long-lived ``ty server`` process."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Self

import ty

from ._lsp import LSPClient


class TyLSP:
    """A running ``ty server`` for one project, passed to the query functions.

    Starting the server is slow, so start it once and make many queries. Use it as
    a context manager so that the server is shut down afterwards. It is not
    thread-safe. Queries read files from disk, so they see saved changes only.
    """

    def __init__(self, root: Path, *, stderr: Path | None = None) -> None:
        """Start the ``ty server`` of the installed ``ty`` package for the project at ``root``.

        The server's stderr (its log) is written to the file ``stderr``, which is
        overwritten, or discarded if ``stderr`` is ``None``.
        """
        self._root = root.resolve()
        self._lsp = LSPClient([ty.find_ty_bin(), "server"], self._root, stderr=stderr)
        try:
            self._lsp.request(
                "initialize",
                {
                    "processId": None,
                    "rootUri": self._root.as_uri(),
                    "workspaceFolders": [
                        {"uri": self._root.as_uri(), "name": self._root.name}
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

    def _notify(self, method: str, params: Any) -> None:
        self._lsp.notify(method, params)

    def _request(self, method: str, params: Any) -> Any:
        return self._lsp.request(method, params)

    def _request_many(
        self, method: str, params_list: Sequence[Any], *, window: int = 16
    ) -> list[Any]:
        """Send many requests of one method at once; see ``LSPClient.request_many``."""
        return self._lsp.request_many(method, params_list, window=window)
