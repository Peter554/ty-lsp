from shop import markers
from shop.markers import scoped


@scoped("billing")
def called() -> None: ...


@markers.scoped("billing")
def qualified_and_called() -> None: ...


@markers.scoped(
    "billing",
)
def multiline_call() -> None: ...
