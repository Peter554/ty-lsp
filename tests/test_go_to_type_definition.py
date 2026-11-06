"""End-to-end tests of ``go_to_type_definition`` against ``tests/fixture_project``."""

from ty_lsp import Error, Location, TyLSP, go_to_type_definition

from ._support import PROJECT, find

SHAPES = PROJECT / "shop" / "shapes.py"


def query_at(text: str, name: str) -> Location:
    line = find(SHAPES, text)
    return Location(path=SHAPES, line=line.line, column=line.column + text.index(name))


def test_variable_resolves_to_its_class(lsp: TyLSP) -> None:
    result = go_to_type_definition(lsp, query_at("square = make_square()", "square"))
    assert result == (
        find(SHAPES, "class Square", nth=1).model_copy(update={"column": 7}),
    )


def test_class_resolves_to_itself(lsp: TyLSP) -> None:
    result = go_to_type_definition(lsp, query_at("class Circle(Shape)", "Circle"))
    assert result == (find(SHAPES, "Circle").model_copy(),)


def test_unresolvable_position_is_empty_or_error(lsp: TyLSP) -> None:
    result = go_to_type_definition(lsp, query_at("def make_square", "def"))
    assert result == () or isinstance(result, Error)
