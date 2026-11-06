class Item:
    def __init__(self, name: str) -> None:
        self.name = name

    def label(self) -> str:
        return self.name.title()


def make_item(name: str) -> Item:
    return Item(name)
