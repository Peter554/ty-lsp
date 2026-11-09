"""End-to-end tests of ``find_implementations`` against ``tests/fixture_project``."""

from ty_lsp import Location, TyLSP, find_implementations

from ._support import PROJECT, find, name_in

RENDERERS = PROJECT / "shop" / "renderers.py"


def render(nth: int) -> Location:
    """The name of the ``nth`` ``render`` method."""
    line = find(RENDERERS, "def render", nth=nth)
    return line.model_copy(update={"column": line.column + len("def ")})


def implementations(lsp: TyLSP, query: Location) -> set[Location]:
    result = find_implementations(lsp, query)
    assert isinstance(result, tuple), result
    return set(result)


RENDERER = name_in(RENDERERS, "class Renderer:", "Renderer")
HTML = name_in(RENDERERS, "class HtmlRenderer(", "HtmlRenderer")
FANCY = name_in(RENDERERS, "class FancyHtmlRenderer(", "FancyHtmlRenderer")
PLAIN = name_in(RENDERERS, "class PlainRenderer(", "PlainRenderer")


def test_class_gives_its_subclasses_at_any_depth_and_itself(lsp: TyLSP) -> None:
    assert implementations(lsp, RENDERER) == {RENDERER, HTML, FANCY, PLAIN}


def test_method_gives_its_overrides_at_any_depth_and_itself(lsp: TyLSP) -> None:
    base, html, fancy = render(1), render(2), render(3)
    assert implementations(lsp, base) == {base, html, fancy}
    assert implementations(lsp, html) == {html, fancy}


def test_class_without_subclasses_gives_only_itself(lsp: TyLSP) -> None:
    assert implementations(lsp, PLAIN) == {PLAIN}
