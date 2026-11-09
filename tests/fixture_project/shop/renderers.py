class Renderer:
    def render(self) -> str:
        return ""


class HtmlRenderer(Renderer):
    def render(self) -> str:
        return "<p></p>"


class FancyHtmlRenderer(HtmlRenderer):
    def render(self) -> str:
        return "<p class='fancy'></p>"


class PlainRenderer(Renderer): ...
