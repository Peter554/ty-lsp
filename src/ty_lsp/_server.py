"""A long-lived ``ty server`` that later CLI commands send their queries to.

Starting ``ty server`` and letting it index the project is most of the time of a
query, so ``ty-lsp serve`` does it once. Other ``ty-lsp`` commands in the same
project find the server's Unix socket and send it their arguments; it runs them
the way the command line would, and sends back the output and exit code. Without a
server they run as before.

With ``--start-server`` a command starts the server itself if none is running, and
the server stops after a while without requests (``serve --idle-timeout``).

The ty server does not watch the files, so a watcher (``watchfiles``) collects the
changes, and they are sent to ty before the next request.
"""

import contextlib
import hashlib
import io
import json
import os
import shlex
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from collections.abc import Callable, Generator, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import watchfiles

from ._ty_lsp import TyLSP

type Run = Callable[[list[str], TyLSP], int]
"""Runs the command line (the arguments after ``ty-lsp``) with the shared server."""

_SETTLE = 0.1
"""Seconds to wait before each request. The watcher reports a change a few tens of
milliseconds late, so a query sent right after an edit would otherwise miss it."""

_START_TIMEOUT = 60.0
"""Seconds to wait for a server that was just started."""

AUTO_IDLE_MINUTES = 5
"""How long a server started by ``--start-server`` waits for a request before stopping."""

_NOT_FORWARDED = {"serve", "stop", "claude-skill", "install-claude-skill"}
_KINDS: dict[watchfiles.Change, Literal[1, 2, 3]] = {
    watchfiles.Change.added: 1,
    watchfiles.Change.modified: 2,
    watchfiles.Change.deleted: 3,
}


def socket_path(root: Path) -> Path:
    """Where the server for the project at ``root`` listens."""
    digest = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"ty-lsp-{os.getuid()}" / f"{digest}.sock"


def _root_of(argv: Sequence[str]) -> Path:
    """The ``--root`` of a command line (the current directory by default)."""
    for i, arg in enumerate(argv):
        if arg == "--root" and i + 1 < len(argv):
            return Path(argv[i + 1])
        if arg.startswith("--root="):
            return Path(arg.removeprefix("--root="))
    return Path()


def log_path(root: Path) -> Path:
    """Where the log of a server started by ``--start-server`` goes."""
    return socket_path(root).with_suffix(".log")


def _connect(root: Path) -> socket.socket | None:
    """A connection to the server for the project at ``root``, if one is running."""
    conn = socket.socket(socket.AF_UNIX)
    try:
        conn.connect(str(socket_path(root)))
    except (FileNotFoundError, ConnectionRefusedError):
        conn.close()
        return None
    return conn


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
        conn.shutdown(socket.SHUT_WR)
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


class _Changes:
    """The Python files changed under ``root`` since they were last taken."""

    def __init__(self, root: Path) -> None:
        self._pending: dict[Path, Literal[1, 2, 3]] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._watch, args=(root,), daemon=True)
        self._thread.start()

    def _watch(self, root: Path) -> None:
        python = watchfiles.PythonFilter(extra_extensions=(".pyi",))
        for batch in watchfiles.watch(
            root, watch_filter=python, stop_event=self._stop, debounce=5, step=10
        ):
            with self._lock:
                for change, path in batch:
                    self._pending[Path(path)] = _KINDS[change]

    def take(self) -> list[tuple[Path, Literal[1, 2, 3]]]:
        with self._lock:
            taken, self._pending = list(self._pending.items()), {}
        return taken

    def stop(self) -> None:
        self._stop.set()
        self._thread.join()


class Server:
    """Answers command lines sent by ``forward``, one at a time, until stopped."""

    def __init__(
        self, root: Path, run: Run, *, idle_timeout: float | None = None
    ) -> None:
        """``idle_timeout`` is the seconds without a request after which it stops."""
        self._root = root.resolve()
        self._run = run
        self._idle_timeout = idle_timeout
        self._stopped = threading.Event()
        self.ready = threading.Event()
        """Set once the server is listening."""
        self.path = socket_path(self._root)

    def stop(self) -> None:
        self._stopped.set()

    def serve_forever(self) -> None:
        """Start ty and listen, until ``stop`` is called. Raises if one is running."""
        self.path.parent.mkdir(mode=0o700, exist_ok=True)
        if self.path.exists():
            with (
                contextlib.suppress(ConnectionRefusedError),
                socket.socket(socket.AF_UNIX) as probe,
            ):
                probe.connect(str(self.path))
                raise RuntimeError(f"a server is already running ({self.path})")
            self.path.unlink()  # left behind by a server that died
        changes = _Changes(self._root)
        try:
            with TyLSP(self._root) as lsp, socket.socket(socket.AF_UNIX) as listener:
                listener.bind(str(self.path))
                listener.listen()
                listener.settimeout(0.2)
                self.ready.set()
                _log(f"ready, listening on {self.path}")
                last_request = time.monotonic()
                while not self._stopped.is_set():
                    try:
                        conn, _ = listener.accept()
                    except TimeoutError:
                        idle = time.monotonic() - last_request
                        if self._idle_timeout is not None and idle > self._idle_timeout:
                            _log(f"no request for {idle / 60:.0f} minutes")
                            break
                        continue
                    with conn:
                        try:
                            self._answer(conn, lsp, changes)
                        except Exception:  # noqa: BLE001 (keep serving)
                            _log("request failed:\n" + traceback.format_exc())
                    last_request = time.monotonic()
        finally:
            changes.stop()
            self.path.unlink(missing_ok=True)
            _log("stopped")

    def _answer(self, conn: socket.socket, lsp: TyLSP, changes: _Changes) -> None:
        started = time.monotonic()
        request: dict[str, Any] = json.loads(conn.makefile("rb").readline())
        if request.get("stop"):
            _log("stop requested")
            self.stop()
            conn.sendall(b"{}")
            return
        time.sleep(_SETTLE)  # let the watcher report a change made just before
        taken = changes.take()
        if taken:
            lsp._files_changed(taken)
        stdout, stderr = io.StringIO(), io.StringIO()
        cwd = Path.cwd()
        os.chdir(request["cwd"])  # relative paths are relative to the caller
        try:
            with (
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
                _stdin(request["stdin"]),
            ):
                code = self._run(request["argv"], lsp)
        finally:
            os.chdir(cwd)
        reply = {"stdout": stdout.getvalue(), "stderr": stderr.getvalue(), "code": code}
        conn.sendall(json.dumps(reply).encode())
        _log(
            f"{shlex.join(request['argv'])}  (in {request['cwd']}) -> exit {code} "
            f"in {time.monotonic() - started:.2f}s" + self._describe(taken)
        )

    def _describe(self, changes: Sequence[tuple[Path, Literal[1, 2, 3]]]) -> str:
        """A note of the file changes sent to ty before a request, for the log."""
        if not changes:
            return ""
        names = [str(path.relative_to(self._root)) for path, _ in changes[:3]]
        more = f" and {len(changes) - 3} more" if len(changes) > 3 else ""
        return f"; {len(changes)} changed file(s): {', '.join(names)}{more}"


def _log(message: str) -> None:
    """Print a line of the server's log (to stderr) with the time."""
    print(f"{datetime.now():%H:%M:%S} {message}", file=sys.stderr, flush=True)


@contextlib.contextmanager
def _stdin(text: str | None) -> Generator[None]:
    old, sys.stdin = sys.stdin, io.StringIO(text or "")
    try:
        yield
    finally:
        sys.stdin = old
