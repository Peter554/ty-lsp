"""Where the servers' sockets and logs are, and how a server describes itself."""

import hashlib
import os
import tempfile
from pathlib import Path

from .._common import Frozen


def socket_dir() -> Path:
    """The directory of the sockets (and logs) of this user's servers."""
    return Path(tempfile.gettempdir()) / f"ty-lsp-{os.getuid()}"


def socket_path(root: Path) -> Path:
    """Where the server for the project at ``root`` listens."""
    digest = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
    return socket_dir() / f"{digest}.sock"


def log_path(root: Path) -> Path:
    """Where the log of a server started by ``--start-server`` goes."""
    return socket_path(root).with_suffix(".log")


class ServerInfo(Frozen):
    """A running server, as it describes itself."""

    root: Path
    pid: int
    started: float
    """When it started: seconds since the epoch."""
    last_request: float | None
    """When it last answered a request (seconds since the epoch), or ``None`` if never."""
    requests: int
