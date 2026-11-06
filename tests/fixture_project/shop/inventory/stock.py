class Stock:
    def __init__(self) -> None:
        self.level = 0

    def adjust(self, delta: int) -> None:
        self.level += delta


def reserve(stock: Stock) -> None:
    stock.adjust(-1)
