from collections.abc import Callable


def internal[F: Callable[..., object]](fn: F) -> F:
    return fn


def scoped[F: Callable[..., object]](scope: str) -> Callable[[F], F]:
    def decorate(fn: F) -> F:
        return fn

    return decorate


def _identity[F: Callable[..., object]](fn: F) -> F:
    return fn


alias_marker = _identity
