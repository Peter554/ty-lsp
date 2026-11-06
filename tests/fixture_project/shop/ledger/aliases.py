from shop import markers
from shop import markers as é
from shop.markers import internal as private


@private
def aliased() -> None: ...


@markers.internal
async def qualified() -> None: ...


@é.internal
def unicode_alias() -> None: ...
