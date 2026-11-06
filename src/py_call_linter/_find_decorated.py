"""Find the definitions decorated with a given decorator.

ty reports a decorator being applied as a call, so the call sites of the decorator
are where it is used. Each call site that sits in the decorator part of a
definition (between where the definition starts and its name) belongs to it.
"""

from collections import defaultdict
from pathlib import Path

from ._find_callers import CallerQuery, find_direct_callers
from ._find_symbol import SymbolQuery, find_symbol, list_symbols
from ._ty_lsp import TyLSP
from ._utils import Error, Location, Result


def _position(location: Location) -> tuple[int, int]:
    return location.line, location.column


def find_decorated(
    lsp: TyLSP, root: Path, decorator: Location | SymbolQuery
) -> Result[tuple[Location, ...]]:
    """Return where every definition decorated with ``decorator`` is named.

    ``decorator`` identifies the decorator's definition in one of two ways:

    - a ``Location``: the position of the decorator's name where it is defined
    - a ``SymbolQuery``: its file and name (dotted for nested names), which is
      looked up with ``find_symbol``. If the name is defined more than once, such
      as in ``if``/``else`` branches or by redefinition, a definition decorated
      with any of them matches. A name that is not defined in the file is an
      ``Error``.

    Every function, method and class in a file under ``root`` that is decorated
    with it is returned as the position of its name, sorted by path, line and
    column, so the result can be passed on to ``find_references`` or
    ``find_direct_callers``. ``root`` must be a directory.

    The decorator must be a function or class: ty does not track calls to
    variables (``deco = make_deco()``), so a decorator like that finds nothing,
    without an ``Error``. Decorators are matched by what they resolve to (using
    ``find_direct_callers``), not by name: ``import ... as`` aliases, qualified names and re-exports all
    match, and a different decorator with the same name does not. Both ``@name``
    and ``@name(...)`` are found. A call to the decorator inside the arguments of
    another decorator is counted too.

    Per-query failures are returned as ``Error``; a crashed type server raises
    ``RuntimeError``.
    """
    root = root.resolve()
    if not root.is_dir():
        return Error(f"{root} is not a directory", None)

    if isinstance(decorator, SymbolQuery):
        found = find_symbol(lsp, decorator)
        if isinstance(found, Error):
            return found
        if not found:
            return Error(f"{decorator.name!r} is not defined in {decorator.path}", None)
        decorator_locations = set(found)
    else:
        decorator_locations = {decorator}

    # An overloaded decorator reports the same call sites for each overload, so
    # collect them in a set.
    call_sites_by_file: dict[Path, set[Location]] = defaultdict(set)
    for location in decorator_locations:
        callers = find_direct_callers(lsp, CallerQuery(**location.model_dump()))
        if isinstance(callers, Error):
            return callers
        for caller in callers:
            for call_site in caller.call_sites:
                if call_site.path.is_relative_to(root):
                    call_sites_by_file[call_site.path].add(call_site)

    decorated: set[Location] = set()
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
                decorated.add(max(headers, key=lambda s: _position(s.start)).location)
    return tuple(sorted(decorated, key=lambda l: (str(l.path), l.line, l.column)))
