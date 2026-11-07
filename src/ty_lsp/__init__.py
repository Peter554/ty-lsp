"""Query Python code with ty's language server.

[Source code and CLI documentation on GitHub](https://github.com/Peter554/ty-lsp).

Start a ``TyLSP`` for a project, then pass it to the query functions. Positions
are ``Location``s (1-based), and each query returns its result or an ``Error``::

    with TyLSP(Path("my_project")) as lsp:
        callers = find_all_callers(lsp, Location(path=path, line=3, column=5))
        if not isinstance(callers, Error):
            ...
"""

from ._common import Error, Location, Result
from ._queries._calls._build_call_graph import CallGraph, build_call_graph
from ._queries._calls._common import Callee
from ._queries._calls._find_callees import find_all_callees, find_direct_callees
from ._queries._calls._find_callers import Caller, find_all_callers, find_direct_callers
from ._queries._definitions._find_definition import find_definition
from ._queries._definitions._find_file import find_file
from ._queries._definitions._find_type_definition import find_type_definition
from ._queries._references._find_references import find_references
from ._queries._symbols._find_symbol import SymbolQuery, find_symbol
from ._queries._symbols._list_symbols import Symbol, list_symbols
from ._queries._types._find_subtypes import (
    Subtype,
    find_all_subtypes,
    find_direct_subtypes,
)
from ._queries._types._find_supertypes import (
    Supertype,
    find_all_supertypes,
    find_direct_supertypes,
)
from ._ty_lsp import TyLSP

__all__ = [  # noqa: RUF022 (ordered for the docs)
    # Server
    "TyLSP",
    # Queries
    "find_definition",
    "find_type_definition",
    "find_file",
    "find_references",
    "list_symbols",
    "find_symbol",
    "find_direct_callers",
    "find_all_callers",
    "find_direct_callees",
    "find_all_callees",
    "build_call_graph",
    "find_direct_subtypes",
    "find_all_subtypes",
    "find_direct_supertypes",
    "find_all_supertypes",
    # Query and result types
    "SymbolQuery",
    "Symbol",
    "Caller",
    "Callee",
    "CallGraph",
    "Subtype",
    "Supertype",
    "Location",
    "Result",
    "Error",
]
