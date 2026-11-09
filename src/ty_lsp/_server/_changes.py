"""Collects the file changes in a project, as the ty server does not watch them."""

import threading
from pathlib import Path
from typing import Literal

import watchfiles

_KINDS: dict[watchfiles.Change, Literal[1, 2, 3]] = {
    watchfiles.Change.added: 1,
    watchfiles.Change.modified: 2,
    watchfiles.Change.deleted: 3,
}


class Changes:
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
