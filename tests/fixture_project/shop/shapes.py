class Shape: ...


class Polygon(Shape): ...


class Square(Polygon): ...


class Circle(Shape): ...


class Drawable: ...


class Sprite(Circle, Drawable): ...


def make_square() -> Square:
    return Square()


square = make_square()
