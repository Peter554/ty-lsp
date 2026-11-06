"""Call graph shapes: a diamond, mutual recursion and self recursion."""


def leaf() -> None: ...


def mid_a() -> None:
    leaf()


def mid_b() -> None:
    leaf()


def top() -> None:
    mid_a()
    mid_b()


def ping(n: int) -> None:
    if n:
        pong(n - 1)


def pong(n: int) -> None:
    ping(n - 1)


def start() -> None:
    ping(3)


def countdown(n: int) -> None:
    if n:
        countdown(n - 1)


def helper() -> None: ...


def twice() -> None:
    helper()
    helper()
