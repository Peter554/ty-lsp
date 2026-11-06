"""End-to-end tests of ``list_symbols`` against ``tests/fixture_project``."""

from ty_lsp import Error, TyLSP, list_symbols

from ._support import PROJECT, find, name_in

SHOP = PROJECT / "shop"
ENTRIES = SHOP / "ledger" / "entries.py"
ALIASES = SHOP / "ledger" / "aliases.py"
MARKERS = SHOP / "markers.py"


def symbols_of(lsp: TyLSP, path):
    result = list_symbols(lsp, path)
    assert isinstance(result, tuple), result
    return {symbol.name: symbol for symbol in result}, [s.name for s in result]


def test_lists_every_symbol_in_file_order_with_nested_ones_after_their_parent(
    lsp: TyLSP,
) -> None:
    _, names = symbols_of(lsp, ENTRIES)
    assert names == [
        "post",
        "public",
        "cached",
        "café",
        "Ledger",
        "close",  # method, after its class
        "open",
        "Archive",
        "closure_factory",
        "nested",  # function in a function
        "conditional",  # inside an if
        "passes_marker_as_argument",
    ]


def test_location_is_the_position_of_the_name(lsp: TyLSP) -> None:
    by_name, _ = symbols_of(lsp, ENTRIES)
    assert by_name["post"].location == name_in(ENTRIES, "def post", "post")
    assert by_name["café"].location == name_in(ENTRIES, "def café", "café")
    assert by_name["Ledger"].location == name_in(ENTRIES, "class Ledger", "Ledger")
    assert by_name["close"].location == name_in(ENTRIES, "    def close", "close")
    assert by_name["nested"].location == name_in(ENTRIES, "    def nested", "nested")
    assert all(symbol.location.path == ENTRIES for symbol in by_name.values())


def test_start_of_a_decorated_definition_is_its_first_decorator(lsp: TyLSP) -> None:
    by_name, _ = symbols_of(lsp, ENTRIES)
    assert by_name["post"].start == find(ENTRIES, "@internal", nth=1)
    # With several decorators, the first one.
    assert by_name["cached"].start == find(ENTRIES, "@functools.cache")
    # Indented decorators start at their own indentation.
    assert by_name["close"].start == name_in(ENTRIES, "    @internal", "@internal")
    assert by_name["nested"].start.column == by_name["nested"].location.column - 4


def test_start_of_an_undecorated_definition_is_its_keyword(lsp: TyLSP) -> None:
    by_name, _ = symbols_of(lsp, ENTRIES)
    assert by_name["public"].start == find(ENTRIES, "def public")
    assert by_name["Ledger"].start == find(ENTRIES, "class Ledger")
    assert by_name["open"].start == name_in(ENTRIES, "    def open", "def open")


def test_async_function_name_comes_after_async_def(lsp: TyLSP) -> None:
    by_name, _ = symbols_of(lsp, ALIASES)
    qualified = by_name["qualified"]
    assert qualified.location == name_in(ALIASES, "async def qualified", "qualified")
    assert qualified.start == find(ALIASES, "@markers.internal")


def test_variables_are_symbols_and_nested_functions_are_listed(lsp: TyLSP) -> None:
    by_name, names = symbols_of(lsp, MARKERS)
    variable = by_name["alias_marker"]
    assert variable.location == name_in(MARKERS, "alias_marker =", "alias_marker")
    assert variable.start == variable.location
    # ``decorate`` is defined inside ``scoped``.
    assert names.index("decorate") == names.index("scoped") + 1


def test_imports_are_not_symbols(lsp: TyLSP) -> None:
    _, names = symbols_of(lsp, ENTRIES)
    assert "functools" not in names
    assert "internal" not in names


def test_file_without_definitions(lsp: TyLSP) -> None:
    assert list_symbols(lsp, SHOP / "ledger" / "__init__.py") == ()


def test_missing_file(lsp: TyLSP) -> None:
    result = list_symbols(lsp, SHOP / "missing.py")
    assert result == () or isinstance(result, Error)
