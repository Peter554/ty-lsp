import dataclasses
from pathlib import Path

import pydantic


class Frozen(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True)


class Location(Frozen):
    path: Path
    line: int  # 1-based
    column: int  # 1-based

    def __str__(self) -> str:
        return f"{self.path}:{self.line}:{self.column}"


@dataclasses.dataclass(frozen=True)
class Error:
    message: str
    exception: Exception | None


type Result[T] = T | Error
