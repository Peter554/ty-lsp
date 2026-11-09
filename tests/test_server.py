"""Tests of ``ty-lsp serve`` and the commands that use it, on a copy of ``tests/fixture_project``."""

import contextlib
import io
import os
import shutil
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from ty_lsp._cli import _run_command_line, app
from ty_lsp._server import Server, forward, list_servers, stop
from ty_lsp._server._common import log_path, socket_path

from ._support import PROJECT


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Path]:
    root = tmp_path.resolve() / "project"
    shutil.copytree(PROJECT, root, ignore=shutil.ignore_patterns("__pycache__"))
    server = Server(root, _run_command_line)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    assert server.ready.wait(timeout=30)
    old = Path.cwd()
    os.chdir(root)
    try:
        yield root
    finally:
        os.chdir(old)
        server.stop()
        thread.join()


def ask(root: Path, *args: str) -> tuple[int | None, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = forward([*args, "-f", "text", "--root", str(root)])
    return code, out.getvalue()


def test_without_a_server_nothing_is_forwarded(tmp_path: Path) -> None:
    assert ask(tmp_path, "definition", "a.py:1:1") == (None, "")


def test_a_command_runs_on_the_server(project: Path) -> None:
    code, out = ask(project, "subtypes", "shop/shapes.py:Polygon")
    assert code == 0
    assert out.splitlines()[1:] == [
        "Triangle shop/shape_users.py:4:7 subtype of shop/shapes.py:4:7",
        "Square shop/shapes.py:7:7 subtype of shop/shapes.py:4:7",
    ]


def test_a_failed_query_gives_exit_code_1(project: Path) -> None:
    code, out = ask(project, "definition", "nope.py:1:1")
    assert code == 1
    assert "error: file not found: nope.py" in out


def test_edits_and_new_files_are_seen(project: Path) -> None:
    ask(project, "subtypes", "shop/shapes.py:Shape")
    shapes = project / "shop" / "shapes.py"
    shapes.write_text(shapes.read_text() + "\n\nclass Hexagon(Shape): ...\n")
    (project / "shop" / "extra.py").write_text(
        "from shop.shapes import Shape\n\n\nclass Octagon(Shape): ...\n"
    )
    _, out = ask(project, "subtypes", "shop/shapes.py:Shape")
    assert "Hexagon shop/shapes.py:" in out
    assert "Octagon shop/extra.py:" in out

    (project / "shop" / "extra.py").unlink()
    _, out = ask(project, "subtypes", "shop/shapes.py:Shape")
    assert "Octagon" not in out


def test_requests_are_logged(project: Path, capfd: pytest.CaptureFixture[str]) -> None:
    ask(project, "definition", "nope.py:1:1")
    (project / "shop" / "extra.py").write_text("x = 1\n")
    ask(project, "subtypes", "shop/shapes.py:Shape")
    log = capfd.readouterr().err
    assert "definition nope.py:1:1 -f text --root" in log
    assert "-> exit 1 in" in log
    assert "-> exit 0 in" in log
    assert "1 changed file(s): shop/extra.py" in log


def wait_until_stopped(root: Path) -> None:
    deadline = time.monotonic() + 30
    while socket_path(root).exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not socket_path(root).exists()


def test_start_server_starts_one_that_later_commands_use_and_stop_stops(
    tmp_path: Path,
) -> None:
    root = tmp_path.resolve() / "project"
    shutil.copytree(PROJECT, root, ignore=shutil.ignore_patterns("__pycache__"))
    old = Path.cwd()
    os.chdir(root)
    try:
        assert ask(root, "subtypes", "shop/shapes.py:Polygon") == (None, "")  # none yet
        code, out = ask(root, "subtypes", "shop/shapes.py:Polygon", "--start-server")
        assert code == 0
        assert "Triangle shop/shape_users.py:4:7" in out
        assert socket_path(root).exists()
        # Found without the flag now.
        assert ask(root, "subtypes", "shop/shapes.py:Polygon")[0] == 0
        log = log_path(root).read_text()  # the started server's log
        assert "ready, listening on" in log
        assert log.count("subtypes shop/shapes.py:Polygon") == 2
        assert stop(root) is True
        wait_until_stopped(root)
        assert stop(root) is False
    finally:
        os.chdir(old)
        stop(root)
        log_path(root).unlink(missing_ok=True)


def test_the_server_stops_after_the_idle_timeout(tmp_path: Path) -> None:
    root = tmp_path.resolve() / "project"
    shutil.copytree(PROJECT, root, ignore=shutil.ignore_patterns("__pycache__"))
    server = Server(root, _run_command_line, idle_timeout=0.5)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    thread.join(timeout=30)
    assert not thread.is_alive()
    assert not socket_path(root).exists()


def test_list_servers_describes_the_running_servers(project: Path) -> None:
    (mine,) = [s for s in list_servers() if s.root == project]
    assert (mine.requests, mine.last_request) == (0, None)

    ask(project, "subtypes", "shop/shapes.py:Polygon")
    (mine,) = [s for s in list_servers() if s.root == project]
    assert mine.requests == 1
    assert mine.last_request is not None
    assert mine.last_request >= mine.started


def test_list_servers_command(project: Path, capfd: pytest.CaptureFixture[str]) -> None:
    code = app(["list-servers"], exit_on_error=False, result_action="return_value")
    assert code == 0
    out = capfd.readouterr().out
    (line,) = [line for line in out.splitlines() if str(project) in line]
    assert line.startswith(f"{project}  pid ")
    assert "0 requests, no requests yet" in line


def test_list_servers_is_not_forwarded_to_a_server(project: Path) -> None:
    assert forward(["list-servers", "--root", str(project)]) is None


def test_asking_what_servers_there_are_does_not_keep_one_alive(tmp_path: Path) -> None:
    root = tmp_path.resolve() / "project"
    shutil.copytree(PROJECT, root, ignore=shutil.ignore_patterns("__pycache__"))
    server = Server(root, _run_command_line, idle_timeout=1.0)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    assert server.ready.wait(timeout=30)
    deadline = time.monotonic() + 30
    while thread.is_alive() and time.monotonic() < deadline:
        list_servers()  # more often than the timeout
        time.sleep(0.1)
    assert not thread.is_alive()
    thread.join()
