from collections.abc import Callable


def internal[F: Callable[..., object]](fn: F) -> F:
    return fn
