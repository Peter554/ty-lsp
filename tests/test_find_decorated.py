"""End-to-end tests of ``find_decorated`` against ``tests/fixture_project``."""

from py_call_linter import Error, SymbolQuery, TyLSP, find_decorated

from ._support import PROJECT, name_in

SHOP = PROJECT / "shop"
LEDGER = SHOP / "ledger"
ENTRIES = LEDGER / "entries.py"
ALIASES = LEDGER / "aliases.py"
LOOKALIKE = LEDGER / "lookalike.py"

INTERNAL = name_in(SHOP / "markers.py", "def internal", "internal")
OTHER_INTERNAL = name_in(SHOP / "other_markers.py", "def internal", "internal")


def test_finds_every_kind_of_decorated_definition(lsp: TyLSP) -> None:
    result = find_decorated(lsp, PROJECT, INTERNAL)
    assert isinstance(result, tuple), result
    assert set(result) == {
        name_in(ENTRIES, "def post", "post"),  # plain function
        name_in(ENTRIES, "def cached", "cached"),  # one of several decorators
        name_in(ENTRIES, "def café", "café"),  # non-ASCII name
        name_in(ENTRIES, "    def close", "close"),  # method
        name_in(ENTRIES, "class Archive", "Archive"),  # class
        name_in(ENTRIES, "    def nested", "nested"),  # nested function
        name_in(ENTRIES, "    def conditional", "conditional"),  # inside an if
        name_in(ALIASES, "def aliased", "aliased"),  # import ... as
        name_in(ALIASES, "def qualified", "qualified"),  # @module.name, async
        name_in(ALIASES, "def unicode_alias", "unicode_alias"),  # non-ASCII alias
    }


def test_results_are_sorted(lsp: TyLSP) -> None:
    result = find_decorated(lsp, PROJECT, INTERNAL)
    assert isinstance(result, tuple), result
    keys = [(str(loc.path), loc.line, loc.column) for loc in result]
    assert keys == sorted(keys)


def test_decorator_is_matched_by_definition_not_by_name(lsp: TyLSP) -> None:
    result = find_decorated(lsp, PROJECT, OTHER_INTERNAL)
    assert result == (name_in(LOOKALIKE, "def not_marked", "not_marked"),)


def test_undecorated_names_are_not_returned(lsp: TyLSP) -> None:
    result = find_decorated(lsp, PROJECT, INTERNAL)
    assert isinstance(result, tuple), result
    assert name_in(ENTRIES, "def public", "public") not in result
    assert name_in(ENTRIES, "    def open", "open") not in result
    assert name_in(ENTRIES, "def passes_marker", "passes_marker") not in result


def test_decorator_that_is_never_used(lsp: TyLSP) -> None:
    unused = name_in(SHOP / "pricing.py", "def total", "total")
    assert find_decorated(lsp, PROJECT, unused) == ()


def test_root_that_is_not_a_directory_is_an_error(lsp: TyLSP) -> None:
    assert isinstance(find_decorated(lsp, PROJECT / "missing", INTERNAL), Error)


def test_decorator_factories_called_with_arguments(lsp: TyLSP) -> None:
    factories = LEDGER / "factories.py"
    scoped = name_in(SHOP / "markers.py", "def scoped", "scoped")
    assert find_decorated(lsp, PROJECT, scoped) == (
        name_in(factories, "def called", "called"),  # @name(...)
        name_in(factories, "def qualified_and_called", "qualified_and_called"),
        name_in(factories, "def multiline_call", "multiline_call"),  # @pkg.name(...)
    )


def test_decorator_named_by_file_and_name(lsp: TyLSP) -> None:
    by_name = find_decorated(
        lsp, PROJECT, SymbolQuery(path=SHOP / "markers.py", name="internal")
    )
    assert by_name == find_decorated(lsp, PROJECT, INTERNAL)
    assert by_name


def test_decorator_that_is_a_variable_finds_nothing(lsp: TyLSP) -> None:
    # Known limitation: ty does not track calls to variables, and this is not an
    # error, so it looks the same as a decorator that is never used.
    query = SymbolQuery(path=SHOP / "markers.py", name="alias_marker")
    assert find_decorated(lsp, PROJECT, query) == ()


def test_decorator_name_not_in_file_is_an_error(lsp: TyLSP) -> None:
    query = SymbolQuery(path=SHOP / "markers.py", name="nope")
    assert isinstance(find_decorated(lsp, PROJECT, query), Error)
