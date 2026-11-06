"""End-to-end tests of ``find_references`` against ``tests/fixture_project``."""

from py_call_linter import Location, ReferenceQuery, TyLSP, find_references

from ._support import PROJECT, name_in

INVENTORY = PROJECT / "shop" / "inventory"
STOCK = INVENTORY / "stock.py"
INIT = INVENTORY / "__init__.py"
AUDIT = INVENTORY / "audit.py"
REPORT = INVENTORY / "deep" / "report.py"
CHECKOUT = PROJECT / "shop" / "checkout.py"


def references(lsp: TyLSP, at: Location) -> set[Location]:
    result = find_references(lsp, ReferenceQuery(**at.model_dump()))
    assert isinstance(result, tuple), result
    assert list(result) == sorted(
        result, key=lambda loc: (str(loc.path), loc.line, loc.column)
    )
    return set(result)


RESERVE_DEF = name_in(STOCK, "def reserve(", "reserve")
RESERVE_REFERENCES = {
    name_in(INIT, "import Stock, reserve", "reserve"),  # re-export
    name_in(AUDIT, "import Stock, reserve", "reserve"),  # import in the package
    name_in(AUDIT, "    reserve(stock)", "reserve"),  # call
    name_in(REPORT, "import Stock, reserve", "reserve"),  # import from a subpackage
    name_in(REPORT, "return reserve", "reserve"),  # use that is not a call
    name_in(CHECKOUT, "import Stock, reserve", "reserve"),  # import via re-export
    name_in(CHECKOUT, "    reserve(stock)", "reserve"),  # call
}


def test_function_references_cover_calls_imports_and_non_call_uses(lsp: TyLSP) -> None:
    assert references(lsp, RESERVE_DEF) == RESERVE_REFERENCES


def test_definition_itself_is_not_a_reference(lsp: TyLSP) -> None:
    assert RESERVE_DEF not in references(lsp, RESERVE_DEF)


def test_same_references_from_any_usage(lsp: TyLSP) -> None:
    for usage in (
        name_in(AUDIT, "    reserve(stock)", "reserve"),  # a call
        name_in(CHECKOUT, "import Stock, reserve", "reserve"),  # import via re-export
        name_in(INIT, "import Stock, reserve", "reserve"),  # the re-export itself
    ):
        assert references(lsp, usage) == RESERVE_REFERENCES


def test_class_references_include_annotations_and_construction(lsp: TyLSP) -> None:
    refs = references(lsp, name_in(STOCK, "class Stock", "Stock"))
    assert name_in(STOCK, "(stock: Stock)", "Stock") in refs
    assert name_in(AUDIT, "(stock: Stock)", "Stock") in refs
    assert name_in(CHECKOUT, "Stock()", "Stock") in refs


def test_method_references(lsp: TyLSP) -> None:
    refs = references(lsp, name_in(STOCK, "def adjust", "adjust"))
    assert refs == {
        name_in(STOCK, "stock.adjust(-1)", "adjust"),
        name_in(CHECKOUT, "stock.adjust(1)", "adjust"),
    }


def test_name_without_references(lsp: TyLSP) -> None:
    assert references(lsp, name_in(CHECKOUT, "def checkout", "checkout")) == set()
