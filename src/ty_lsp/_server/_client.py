"""What the other commands use to reach the server for their project."""

import contextlib
import json
import socket
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ._common import ServerInfo, log_path, socket_dir, socket_path

AUTO_IDLE_MINUTES = 5
"""How long a server started by ``--start-server`` waits for a request before stopping."""

_START_TIMEOUT = 60.0
"""Seconds to wait for a server that was just started."""

_INFO_TIMEOUT = 30.0
"""Seconds to wait for a server to describe itself: it may be busy with a request."""

_NOT_FORWARDED = {
    "serve",
    "stop-server",
    "list-servers",
    "claude-skill",
    "install-claude-skill",
}


def _root_of(argv: Sequence[str]) -> Path:
    """The ``--root`` of a command line (the current directory by default)."""
    for i, arg in enumerate(argv):
        if arg == "--root" and i + 1 < len(argv):
            return Path(argv[i + 1])
        if arg.startswith("--root="):
            return Path(arg.removeprefix("--root="))
    return Path()


def _connect_to(path: Path) -> socket.socket | None:
    """A connection to the server listening at ``path``, if there is one."""
    conn = socket.socket(socket.AF_UNIX)
    try:
        conn.connect(str(path))
    except (FileNotFoundError, ConnectionRefusedError):
        conn.close()
        return None
    return conn


def _connect(root: Path) -> socket.socket | None:
    """A connection to the server for the project at ``root``, if one is running."""
    return _connect_to(socket_path(root))


def _start(root: Path) -> socket.socket | None:
    """Start a server for the project at ``root`` in the background and connect to it.

    It outlives this process. Returns ``None`` if it does not come up in time.
    """
    root = root.resolve()
    log_path(root).parent.mkdir(mode=0o700, exist_ok=True)
    with log_path(root).open("ab") as log:
        server = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "from ty_lsp._cli import main; main()",
                "serve",
                "--root",
                str(root),
                "--idle-timeout",
                str(AUTO_IDLE_MINUTES),
            ],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    deadline = time.monotonic() + _START_TIMEOUT
    while time.monotonic() < deadline:
        if conn := _connect(root):
            return conn
        if server.poll() is not None:
            break  # it exited, such as because another server won the race
        time.sleep(0.05)
    return _connect(root)


def _exchange(conn: socket.socket, request: dict[str, Any]) -> dict[str, Any]:
    with conn:
        conn.sendall(json.dumps(request).encode() + b"\n")
        return json.loads(conn.makefile("rb").read())


def forward(argv: list[str]) -> int | None:
    """Run the command line on the server for its project, if there is one.

    Prints the output and returns the exit code, or returns ``None`` if the command
    is not one to forward or there is no server (so it must be run here). With
    ``--start-server`` in the command line, a server is started if there is none.
    """
    if not argv or argv[0].startswith("-") or argv[0] in _NOT_FORWARDED:
        return None
    if {"-h", "--help", "--version"} & set(argv):
        return None
    root = _root_of(argv)
    conn = _connect(root)
    if conn is None and "--start-server" in argv:
        conn = _start(root)
    if conn is None:
        return None
    reply = _exchange(
        conn,
        {
            "argv": argv,
            "cwd": str(Path.cwd()),
            "stdin": sys.stdin.read() if "--stdin" in argv else None,
        },
    )
    sys.stdout.write(reply["stdout"])
    sys.stderr.write(reply["stderr"])
    return reply["code"]


def stop(root: Path) -> bool:
    """Stop the server for the project at ``root``. Returns whether there was one."""
    conn = _connect(root)
    if conn is None:
        return False
    _exchange(conn, {"stop": True})
    return True


def list_servers() -> list[ServerInfo]:
    """The servers of this user that are running, in no particular order.

    A server that does not answer in time is left out, as is a socket left behind by
    a server that died. Asking does not count as a request: it does not keep a server
    from stopping when idle.
    """
    servers: list[ServerInfo] = []
    for path in socket_dir().glob("*.sock"):
        if (conn := _connect_to(path)) is None:
            continue
        conn.settimeout(_INFO_TIMEOUT)
        # A server can stop between our connecting to it and its answering.
        with contextlib.suppress(OSError, json.JSONDecodeError):
            servers.append(ServerInfo.model_validate(_exchange(conn, {"info": True})))
    return servers
