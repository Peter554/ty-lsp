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

    def __init__(self, command: Sequence[str], cwd: Path) -> None:
        self._proc = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
        )
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

    def notify(self, method: str, params: Any) -> None:
        self._send({"method": method, "params": params})

    def request(self, method: str, params: Any) -> Any:
        self._next_id += 1
        request_id = self._next_id
        self._send({"id": request_id, "method": method, "params": params})
        while True:
            message = self._read()
            if "method" in message and "id" in message:
                # "method" + "id" is a request *from* the server (it expects a reply).
                # A response to us has "id" but no "method"; a notification has "method"
                # but no "id".
                self._reply_to_server_request(message)
            elif message.get("id") == request_id:
                # A reply from the server.
                if "error" in message:
                    raise ResponseError(f"{method} failed: {message['error']}")
                return message.get("result")
            # Anything else (diagnostics, log messages, progress) is ignored.

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
