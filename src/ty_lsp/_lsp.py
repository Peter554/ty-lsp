"""A minimal synchronous JSON-RPC/LSP client speaking to a server over stdio."""

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import IO, Any

type JSON = dict[str, object]


class ResponseError(RuntimeError):
    """The server answered a request with an LSP error (the server is still usable)."""


class LSPClient:
    """Runs a language server subprocess and exchanges messages with it."""

    def __init__(
        self, command: Sequence[str], cwd: Path, *, stderr: Path | None = None
    ) -> None:
        """Start ``command`` in ``cwd``; its stderr goes to ``stderr``, or nowhere."""
        self._stderr: IO[bytes] | None = None if stderr is None else stderr.open("wb")
        try:
            self._proc = subprocess.Popen(
                command,
                cwd=cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL if self._stderr is None else self._stderr,
            )
        except BaseException:
            if self._stderr is not None:
                self._stderr.close()
            raise
        assert self._proc.stdin is not None and self._proc.stdout is not None
        self._stdin: IO[bytes] = self._proc.stdin
        self._stdout: IO[bytes] = self._proc.stdout
        self._next_id = 0
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.request("shutdown", None)
            self.notify("exit", None)
        except (OSError, RuntimeError):
            pass
        finally:
            self._stdin.close()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            if self._stderr is not None:
                self._stderr.close()

    def notify(self, method: str, params: Any) -> None:
        self._send({"method": method, "params": params})

    def request(self, method: str, params: Any) -> Any:
        return self.request_many(method, [params], window=1)[0]

    def request_many(
        self, method: str, params_list: Sequence[Any], *, window: int = 16
    ) -> list[Any]:
        """Send many requests of one method, with up to ``window`` outstanding.

        The server can work on several at once, which is faster than one at a time
        for cheap requests. Results are in the order of ``params_list``. If any
        request fails, the rest are still collected and then a ``ResponseError``
        for the first failure is raised.
        """
        results: list[Any] = [None] * len(params_list)
        pending: dict[int, int] = {}  # request id -> index in params_list
        errors: list[tuple[int, Any]] = []
        sent = answered = 0
        while answered < len(params_list):
            while sent < len(params_list) and len(pending) < window:
                self._next_id += 1
                pending[self._next_id] = sent
                self._send(
                    {"id": self._next_id, "method": method, "params": params_list[sent]}
                )
                sent += 1
            message = self._read()
            if "method" in message and "id" in message:
                # "method" + "id" is a request *from* the server (it expects a reply).
                # A response to us has "id" but no "method"; a notification has "method"
                # but no "id".
                self._reply_to_server_request(message)
            elif (index := pending.pop(message.get("id"), None)) is not None:
                if "error" in message:
                    errors.append((index, message["error"]))
                else:
                    results[index] = message.get("result")
                answered += 1
            # Anything else (diagnostics, log messages, progress) is ignored.
        if errors:
            index, error = min(errors)
            raise ResponseError(f"{method} failed: {error}")
        return results

    def _reply_to_server_request(self, message: JSON) -> None:
        # The server may call us mid-request and blocks until we answer, so every
        # server request needs a reply. We have no settings, so answer with null.
        result: Any = None
        if message["method"] == "workspace/configuration":
            # The spec requires one entry per requested item; null means "no config".
            params: Any = message["params"]
            result = [None] * len(params["items"])
        self._send({"id": message["id"], "result": result})

    def _send(self, message: JSON) -> None:
        body = json.dumps({"jsonrpc": "2.0", **message}).encode()
        self._stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
        self._stdin.flush()

    def _read(self) -> JSON:
        length: int | None = None
        while True:
            raw = self._stdout.readline()
            if not raw:
                raise RuntimeError("language server exited unexpectedly")
            header = raw.decode("ascii").strip()
            if not header:
                break
            name, _, value = header.partition(":")
            if name.lower() == "content-length":
                length = int(value)
        if length is None:
            raise RuntimeError("LSP message missing Content-Length header")
        return json.loads(self._stdout.read(length))
