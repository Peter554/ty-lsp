"""Find the file of a module from its dotted path, using ty."""

import keyword
from pathlib import Path

from ..._common import PathError, Result
from ..._ty_lsp import TyLSP
from .._common import capture, parse_locations

_VIRTUAL_DOCUMENT = "untitled:ty-lsp/find_file"
"""A document that exists only in the server, so nothing is written to disk."""


def _find(lsp: TyLSP, module: str) -> Path:
    names = module.split(".")
    if not all(name.isidentifier() and not keyword.iskeyword(name) for name in names):
        raise PathError(f"not a dotted module path: {module!r}")
    # Ask ty where the module in an import statement is defined, like an editor does
    # when you go to the definition of the last name of ``import a.b.c``.
    column = len("import ") + len(module) - len(names[-1])
    document = {"uri": _VIRTUAL_DOCUMENT}
    lsp._notify(
        "textDocument/didOpen",
        {
            "textDocument": {
                **document,
                "languageId": "python",
                "version": 1,
                "text": f"import {module}\n",
            }
        },
    )
    try:
        found = parse_locations(
            lsp._request(
                "textDocument/definition",
                {
                    "textDocument": document,
                    "position": {"line": 0, "character": column},
                },
            )
        )
    finally:
        lsp._notify("textDocument/didClose", {"textDocument": document})
    if not found:
        raise PathError(f"module not found: {module}")
    return found[0].path


def find_file(lsp: TyLSP, module: str) -> Result[Path]:
    """Return the file that defines the module with the dotted path ``module``.

    For example ``"shop.models"`` gives ``.../shop/models.py``, and a package such as
    ``"shop"`` gives its ``__init__.py``. Modules are found as ty would for an import
    in the project, so installed packages and the standard library work too (the
    latter as ty's typeshed stub, a ``.pyi`` file).

    The result is an ``Error`` if no such module is found, or ``module`` is not a
    dotted path of names.
    """
    return capture(_find, lsp, module)
