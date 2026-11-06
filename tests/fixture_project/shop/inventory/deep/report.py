from collections.abc import Callable

from shop.inventory.stock import Stock, reserve


def handler() -> Callable[[Stock], None]:
    return reserve
