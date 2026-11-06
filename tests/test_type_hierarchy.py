"""End-to-end tests of the subtype and supertype queries against ``tests/fixture_project``."""

import re

from ty_lsp import (
    Error,
    Location,
    Subtype,
    TyLSP,
    find_all_subtypes,
    find_all_supertypes,
    find_direct_subtypes,
    find_direct_supertypes,
    list_symbols,
)
from ty_lsp._queries._types._common import walk_hierarchy

from ._support import PROJECT, find, name_in

SHAPES = PROJECT / "shop" / "shapes.py"
USERS = PROJECT / "shop" / "shape_users.py"


def class_at(name: str) -> Location:
    return find(SHAPES, f"class {name}").model_copy(
        update={"column": find(SHAPES, f"class {name}").column + len("class ")}
    )


def sub(name: str) -> Location:
    return class_at(name)


def sup(name: str) -> Location:
    return class_at(name)


def edges(result: object) -> set[tuple[str, str]]:
    """``(name, origin name)`` for each edge, the origin's name read from its source."""
    assert isinstance(result, tuple), result
    found: set[tuple[str, str]] = set()
    for edge in result:
        origin = edge.supertype if isinstance(edge, Subtype) else edge.subtype
        line = origin.path.read_text().splitlines()[origin.line - 1]
        match = re.match(r"class (\w+)", line[: origin.column - 1 + 64].lstrip())
        assert match, line
        found.add((edge.name, match.group(1)))
    return found


def test_direct_subtypes_include_other_modules(lsp: TyLSP) -> None:
    result = find_direct_subtypes(lsp, sub("Polygon"))
    assert edges(result) == {("Square", "Polygon"), ("Triangle", "Polygon")}
    assert isinstance(result, tuple)
    triangle = next(s for s in result if s.name == "Triangle")
    assert triangle.location.path == USERS
    assert triangle.supertype == class_at("Polygon")


def test_all_subtypes_follow_the_whole_tree(lsp: TyLSP) -> None:
    result = find_all_subtypes(lsp, sub("Shape"))
    assert edges(result) == {
        ("Polygon", "Shape"),
        ("Circle", "Shape"),
        ("Square", "Polygon"),
        ("Triangle", "Polygon"),
        ("Sprite", "Circle"),
    }


def test_max_depth_limits_subtypes(lsp: TyLSP) -> None:
    assert find_all_subtypes(lsp, sub("Shape"), max_depth=1) == find_direct_subtypes(
        lsp, sub("Shape")
    )


def test_class_without_subtypes(lsp: TyLSP) -> None:
    assert find_direct_subtypes(lsp, sub("Square")) == ()


def test_direct_supertypes_with_multiple_inheritance(lsp: TyLSP) -> None:
    result = find_direct_supertypes(lsp, sup("Sprite"))
    assert edges(result) == {("Circle", "Sprite"), ("Drawable", "Sprite")}


def test_all_supertypes_end_at_object(lsp: TyLSP) -> None:
    result = find_all_supertypes(lsp, sup("Square"))
    assert edges(result) == {
        ("Polygon", "Square"),
        ("Shape", "Polygon"),
        ("object", "Shape"),
    }


def test_query_from_a_variable_uses_its_type(lsp: TyLSP) -> None:
    use = name_in(SHAPES, "square = make_square()", "square")
    result = find_direct_supertypes(lsp, use)
    assert edges(result) == {("Polygon", "Square")}


def test_non_class_position_is_empty(lsp: TyLSP) -> None:
    query = find(SHAPES, "def make_square")
    assert find_direct_subtypes(lsp, query) == ()


def test_subtypes_match_ty_for_every_class_in_the_project(lsp: TyLSP) -> None:
    """The fast ``implementation``-based search gives ty's own ``subtypes`` answer.

    ty's ``typeHierarchy/subtypes`` is much slower, and also finds subclasses outside
    the project, but the fixture classes have none of those.
    """
    for path in (SHAPES, USERS):
        symbols = list_symbols(lsp, path)
        assert not isinstance(symbols, Error)
        for symbol in symbols:
            slow = {
                (e.name, e.location, e.origin)
                for e in walk_hierarchy(lsp, symbol.location, "subtypes", None)
            }
            fast = find_all_subtypes(lsp, symbol.location)
            assert not isinstance(fast, Error)
            assert {(s.name, s.location, s.supertype) for s in fast} == slow


def test_subtypes_of_a_stdlib_class_are_only_those_in_the_project(lsp: TyLSP) -> None:
    """``Exception`` is defined in typeshed, and has many subclasses outside the project."""
    at = name_in(USERS, "class ShapeError(Exception)", "Exception")
    shape_error = find(USERS, "ShapeError")
    for result in (find_direct_subtypes(lsp, at), find_all_subtypes(lsp, at)):
        assert not isinstance(result, Error)
        assert [(s.name, s.location) for s in result] == [("ShapeError", shape_error)]
