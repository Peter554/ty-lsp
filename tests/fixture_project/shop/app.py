import shop
from shop.models import make_item


def main() -> None:
    item = make_item("apple")
    print(item.label())
    print(shop.total([1.0, 2.0]))
    print(len("not in the project"))
    print(undefined_name())
