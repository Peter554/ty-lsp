import dataclasses
import functools
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import pydantic


class Frozen(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True)


class Location(Frozen):
    path: Path
    line: int  # 1-based
    column: int  # 1-based

    def __str__(self) -> str:
        return f"{self.path}:{self.line}:{self.column}"


class LspPosition(pydantic.BaseModel):
    line: int  # 0-based
    character: int  # 0-based


class LspRange(pydantic.BaseModel):
    start: LspPosition


class LspLocation(pydantic.BaseModel):
    uri: str
    range: LspRange


@functools.cache
def uri_to_path(uri: str) -> Path:
    """The path of a ``file://`` uri. Cached: a few files appear in very many uris."""
    return Path(url2pathname(urlparse(uri).path))


def to_location(uri: str, position: LspPosition) -> Location:
    """Convert an LSP uri and 0-based position to a 1-based ``Location``."""
    return Location(
        path=uri_to_path(uri),
        line=position.line + 1,
        column=position.character + 1,
    )


@dataclasses.dataclass(frozen=True)
class Error:
    message: str
    exception: Exception | None


type Result[T] = T | Error
