"""Find the definitions decorated with a given decorator, using ty.

ty reports a decorator being applied as a call, so the call sites of the decorator
are where it is used. Each call site that sits in the header of a definition (between
where the definition starts, at its first decorator, and its name) belongs to it.
"""

from collections import defaultdict
from pathlib import Path

from ..._common import Error, Location, Result
from ..._ty_lsp import TyLSP
from .._calls._find_callers import find_direct_callers
from ._list_symbols import Symbol, list_symbols


def _position(location: Location) -> tuple[int, int]:
    return location.line, location.column


def find_decorated_by(lsp: TyLSP, decorator: Location) -> Result[tuple[Symbol, ...]]:
    """Return every function, method and class decorated with ``decorator``.

    ``decorator`` is the position of the decorator's name, where it is defined or
    used. Each result is a ``Symbol``: its ``location`` is the position of the name,
    which can be passed on to ``find_references`` or ``find_direct_callers``, and its
    ``start`` is where its first decorator is. They are sorted by path, line and
    column.

    Decorators are matched by what they resolve to, not by name: ``import ... as``
    aliases, qualified names and re-exports all match, and a different decorator with
    the same name does not. Both ``@name`` and ``@name(...)`` are found. A call to the
    decorator inside the arguments of another decorator is counted too.

    The decorator must be a function or class: ty does not track calls to variables
    (``deco = make_deco()``), so a decorator like that finds nothing, without an
    ``Error``.
    """
    callers = find_direct_callers(lsp, decorator)
    if isinstance(callers, Error):
        return callers
    # An overloaded decorator reports the same call sites for each overload, so
    # collect them in a set.
    call_sites_by_file: dict[Path, set[Location]] = defaultdict(set)
    for caller in callers:
        for call_site in caller.call_sites:
            call_sites_by_file[call_site.path].add(call_site)

    decorated: dict[Location, Symbol] = {}
    for path, call_sites in call_sites_by_file.items():
        symbols = list_symbols(lsp, path)
        if isinstance(symbols, Error):
            return symbols
        for call_site in call_sites:
            # A call is in a symbol's decorators if it comes after the symbol starts
            # (its first decorator) but before its name. Nothing else sits there
            # except ``def``/``class``, and the innermost such symbol is the one.
            headers = [
                s
                for s in symbols
                if _position(s.start) <= _position(call_site) < _position(s.location)
            ]
            if headers:
                innermost = max(headers, key=lambda s: _position(s.start))
                decorated[innermost.location] = innermost
    return tuple(
        sorted(
            decorated.values(),
            key=lambda s: (str(s.location.path), s.location.line, s.location.column),
        )
    )
