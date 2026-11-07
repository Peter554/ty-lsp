"""End-to-end tests of ``find_decorated_by`` against ``tests/fixture_project``."""

from ty_lsp import Error, Location, TyLSP, find_decorated_by

from ._support import PROJECT, name_in

SHOP = PROJECT / "shop"
LEDGER = SHOP / "ledger"
ENTRIES = LEDGER / "entries.py"
ALIASES = LEDGER / "aliases.py"
LOOKALIKE = LEDGER / "lookalike.py"

INTERNAL = name_in(SHOP / "markers.py", "def internal", "internal")
OTHER_INTERNAL = name_in(SHOP / "other_markers.py", "def internal", "internal")


def locations(lsp: TyLSP, decorator: Location) -> tuple[Location, ...]:
    result = find_decorated_by(lsp, decorator)
    assert not isinstance(result, Error), result
    return tuple(symbol.location for symbol in result)


def test_finds_every_kind_of_decorated_definition(lsp: TyLSP) -> None:
    assert set(locations(lsp, INTERNAL)) == {
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


def test_results_are_symbols_sorted_by_position(lsp: TyLSP) -> None:
    result = find_decorated_by(lsp, INTERNAL)
    assert not isinstance(result, Error)
    keys = [(str(s.location.path), s.location.line, s.location.column) for s in result]
    assert keys == sorted(keys)
    post = next(s for s in result if s.name == "post")
    assert post.location == name_in(ENTRIES, "def post", "post")
    assert post.start.line < post.location.line  # the decorator comes first


def test_decorator_is_matched_by_definition_not_by_name(lsp: TyLSP) -> None:
    assert locations(lsp, OTHER_INTERNAL) == (
        name_in(LOOKALIKE, "def not_marked", "not_marked"),
    )


def test_undecorated_names_are_not_returned(lsp: TyLSP) -> None:
    found = locations(lsp, INTERNAL)
    assert name_in(ENTRIES, "def public", "public") not in found
    assert name_in(ENTRIES, "    def open", "open") not in found
    assert name_in(ENTRIES, "def passes_marker", "passes_marker") not in found


def test_decorator_that_is_never_used(lsp: TyLSP) -> None:
    unused = name_in(SHOP / "pricing.py", "def total", "total")
    assert locations(lsp, unused) == ()


def test_decorator_factories_called_with_arguments(lsp: TyLSP) -> None:
    factories = LEDGER / "factories.py"
    scoped = name_in(SHOP / "markers.py", "def scoped", "scoped")
    assert locations(lsp, scoped) == (
        name_in(factories, "def called", "called"),  # @name(...)
        name_in(factories, "def qualified_and_called", "qualified_and_called"),
        name_in(factories, "def multiline_call", "multiline_call"),  # @pkg.name(...)
    )


def test_a_usage_of_the_decorator_works_as_well_as_its_definition(lsp: TyLSP) -> None:
    usage = name_in(ENTRIES, "@internal", "internal")
    assert locations(lsp, usage) == locations(lsp, INTERNAL)


def test_decorator_that_is_a_variable_finds_nothing(lsp: TyLSP) -> None:
    # Known limitation: ty does not track calls to variables, and this is not an
    # error, so it looks the same as a decorator that is never used.
    alias_marker = name_in(SHOP / "markers.py", "alias_marker =", "alias_marker")
    assert locations(lsp, alias_marker) == ()


def test_missing_file_is_an_error(lsp: TyLSP) -> None:
    missing = INTERNAL.model_copy(update={"path": SHOP / "nope.py"})
    assert isinstance(find_decorated_by(lsp, missing), Error)
