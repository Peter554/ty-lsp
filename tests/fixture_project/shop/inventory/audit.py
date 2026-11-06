from .stock import Stock, reserve


def check(stock: Stock) -> None:
    reserve(stock)
