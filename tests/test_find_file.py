"""End-to-end tests of ``find_file`` against ``tests/fixture_project``."""

import pytest

from ty_lsp import Error, TyLSP, find_file

from ._support import PROJECT

SHOP = PROJECT / "shop"


@pytest.mark.parametrize(
    ("module", "expected"),
    [
        ("shop", SHOP / "__init__.py"),
        ("shop.models", SHOP / "models.py"),
        ("shop.inventory", SHOP / "inventory" / "__init__.py"),
        ("shop.inventory.audit", SHOP / "inventory" / "audit.py"),
    ],
)
def test_project_modules_and_packages(
    lsp: TyLSP, module: str, expected: object
) -> None:
    assert find_file(lsp, module) == expected


def test_installed_and_standard_library_modules(lsp: TyLSP) -> None:
    pydantic = find_file(lsp, "pydantic")
    assert not isinstance(pydantic, Error)
    assert pydantic.parts[-2:] == ("pydantic", "__init__.py")
    stdlib = find_file(lsp, "os.path")
    assert not isinstance(stdlib, Error)
    assert stdlib.exists()


def test_unknown_module(lsp: TyLSP) -> None:
    for module in ("shop.nope", "nope", "shop.models.nope", "shop.models.py"):
        result = find_file(lsp, module)
        assert isinstance(result, Error)
        assert result.message == f"module not found: {module}"


@pytest.mark.parametrize(
    "module",
    [
        "",
        "shop.",
        ".shop",
        "shop..models",
        "shop/models",
        "a b",
        "class",
        "shop.import",
    ],
)
def test_not_a_dotted_path(lsp: TyLSP, module: str) -> None:
    result = find_file(lsp, module)
    assert isinstance(result, Error)
    assert result.message == f"not a dotted module path: {module!r}"


def test_repeated_lookups_and_nothing_is_written_to_disk(lsp: TyLSP) -> None:
    before = sorted(PROJECT.rglob("*"))
    for _ in range(3):
        assert find_file(lsp, "shop.models") == SHOP / "models.py"
    assert sorted(PROJECT.rglob("*")) == before
