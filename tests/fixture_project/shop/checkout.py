from shop.inventory import Stock, reserve


def checkout() -> None:
    stock = Stock()
    reserve(stock)
    stock.adjust(1)
