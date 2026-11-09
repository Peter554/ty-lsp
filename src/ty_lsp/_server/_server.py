"""The server: listens on a Unix socket and runs the commands sent to it."""

import contextlib
import io
import json
import os
import shlex
import socket
import socketserver
import sys
import threading
import time
import traceback
from collections.abc import Callable, Generator, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from .._ty_lsp import TyLSP
from ._changes import Changes
from ._common import ServerInfo, socket_path

type Run = Callable[[list[str], TyLSP], int]
"""Runs the command line (the arguments after ``ty-lsp``) with the shared server."""

_SETTLE = 0.1
"""Seconds to wait before each request. The watcher reports a change a few tens of
milliseconds late, so a query sent right after an edit would otherwise miss it."""


class _Handler(socketserver.StreamRequestHandler):
    """Reads one line of JSON from a connection and writes back the reply."""

    def handle(self) -> None:
        assert isinstance(self.server, _Listener)
        request = json.loads(self.rfile.readline())
        self.wfile.write(self.server.answer(request))


class _Listener(socketserver.UnixStreamServer):
    """Listens on a Unix socket and answers each connection with ``answer``.

    Connections are answered one at a time: requests change the working directory
    and redirect stdout, and there is one ty server.
    """

    def __init__(self, path: Path, answer: Callable[[dict[str, Any]], bytes]) -> None:
        self.answer = answer
        super().__init__(str(path), _Handler)

    def handle_error(self, request: object, client_address: object) -> None:
        # The default prints to stderr without the time; keep serving either way.
        _log("request failed:\n" + traceback.format_exc())


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
        self._started = time.time()
        self._last_request: float | None = None
        self._idle_since = time.monotonic()
        """When the last request was answered (or the server started), for idleness."""
        self._requests = 0
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
        changes = Changes(self._root)
        try:
            with (
                TyLSP(self._root) as lsp,
                _Listener(
                    self.path, lambda r: self._answer(r, lsp, changes)
                ) as listener,
            ):
                listener.timeout = 0.2  # how often to check for a stop or idleness
                self.ready.set()
                _log(f"ready, listening on {self.path}")
                self._idle_since = time.monotonic()
                while not self._stopped.is_set():
                    idle = time.monotonic() - self._idle_since
                    if self._idle_timeout is not None and idle > self._idle_timeout:
                        _log(f"no request for {idle / 60:.0f} minutes")
                        break
                    listener.handle_request()  # one request, or none in the timeout
        finally:
            changes.stop()
            self.path.unlink(missing_ok=True)
            _log("stopped")

    def _answer(self, request: dict[str, Any], lsp: TyLSP, changes: Changes) -> bytes:
        """The reply to one message: a request, a stop or a probe."""
        started = time.monotonic()
        if request.get("stop"):
            _log("stop requested")
            self.stop()
            return b"{}"
        if request.get("info"):
            info = ServerInfo(
                root=self._root,
                pid=os.getpid(),
                started=self._started,
                last_request=self._last_request,
                requests=self._requests,
            )
            return info.model_dump_json().encode()
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
        self._requests += 1
        self._last_request = time.time()
        self._idle_since = time.monotonic()
        _log(
            f"{shlex.join(request['argv'])}  (in {request['cwd']}) -> exit {code} "
            f"in {time.monotonic() - started:.2f}s" + self._describe(taken)
        )
        return json.dumps(reply).encode()

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
