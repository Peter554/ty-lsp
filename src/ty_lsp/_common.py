import dataclasses
import functools
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import pydantic


class Frozen(pydantic.BaseModel):
    """A pydantic model whose instances are immutable and hashable."""

    model_config = pydantic.ConfigDict(frozen=True)


class Location(Frozen):
    """A position in a source file."""

    path: Path
    line: int
    """1-based."""
    column: int
    """1-based."""

    def __str__(self) -> str:
        return f"{self.path}:{self.line}:{self.column}"


class LspPosition(pydantic.BaseModel):
    """An LSP position."""

    line: int  # 0-based
    character: int  # 0-based


class LspRange(pydantic.BaseModel):
    """An LSP range; only its start is used."""

    start: LspPosition


class LspLocation(pydantic.BaseModel):
    """An LSP location: a uri and a range in it."""

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


class PathError(Exception):
    """A query names a path that is not an existing file."""


def check_file(path: Path) -> None:
    """Raise ``PathError`` unless ``path`` is an existing file.

    ty answers a request about a missing file with an empty result, which would be
    mistaken for "nothing found".
    """
    if not path.exists():
        raise PathError(f"file not found: {path}")
    if not path.is_file():
        raise PathError(f"not a file: {path}")


@dataclasses.dataclass(frozen=True)
class Error:
    """Returned by a query instead of its result when the lookup failed.

    A query fails when the file it names does not exist, the server rejects a
    request, or the server answers with something unexpected. A query that makes several lookups returns the first ``Error``,
    never a partial result. A server that has crashed is not an ``Error``: that
    raises ``RuntimeError``.
    """

    message: str
    exception: Exception
    """The underlying exception."""


type Result[T] = T | Error
"""What a query returns: its result ``T``, or an ``Error``.

Check with ``isinstance(result, Error)``.
"""
