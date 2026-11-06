import functools
import os

from shop.markers import internal


@internal
def post() -> None: ...


def public() -> None: ...


@functools.cache
@internal
def cached() -> int:
    return 1


@internal
def café() -> None: ...


class Ledger:
    @internal
    def close(self) -> None: ...

    def open(self) -> None: ...


@internal
class Archive: ...


def closure_factory() -> None:
    @internal
    def nested() -> None: ...


if os.environ.get("SHOP_FLAG"):

    @internal
    def conditional() -> None: ...


def passes_marker_as_argument() -> None:
    functools.partial(internal)
