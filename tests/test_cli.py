"""Tests of the ``ty-lsp`` command line against ``tests/fixture_project``."""

import io
import json
from pathlib import Path
from typing import Any

import pytest

from ty_lsp._cli import app

from ._support import PROJECT, find

APP = PROJECT / "shop" / "app.py"
MODELS = PROJECT / "shop" / "models.py"


@pytest.fixture
def cli(capfd: pytest.CaptureFixture[str]) -> Any:
    def run(*args: str) -> tuple[int, Any]:
        code = app(
            [*args, "--root", str(PROJECT)],
            exit_on_error=False,
            result_action="return_value",
        )
        out = capfd.readouterr().out
        return code, json.loads(out) if out else None

    return run


def at(location: Any) -> str:
    return f"{location.path}:{location.line}:{location.column}"


def test_queries_from_arguments_give_one_entry_each(cli: Any) -> None:
    use = find(APP, "make_item(")
    code, out = cli("definition", at(use), at(find(APP, "item.label()")))
    target = find(MODELS, "make_item")
    assert code == 0
    assert [e["query"]["raw"] for e in out] == [at(use), at(find(APP, "item.label()"))]
    assert out[0]["query"]["parsed"] == {
        "path": str(use.path),
        "line": use.line,
        "column": use.column,
    }
    assert out[0]["result"] == [
        {"path": str(MODELS), "line": target.line, "column": target.column}
    ]


def test_queries_from_a_file_skip_blanks_and_comments(cli: Any, tmp_path: Path) -> None:
    use = at(find(APP, "make_item("))
    file = tmp_path / "queries.txt"
    file.write_text(f"# a comment\n\n{use}\n  {use}  \n")
    code, out = cli("definition", "--file", str(file))
    assert code == 0
    assert [e["query"]["raw"] for e in out] == [use, use]


def test_queries_from_stdin_with_the_flag(
    cli: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    use = at(find(APP, "make_item("))
    monkeypatch.setattr("sys.stdin", io.StringIO(use + "\n"))
    code, out = cli("definition", "--stdin")
    assert code == 0
    assert [e["query"]["raw"] for e in out] == [use]


def test_empty_input_gives_an_empty_list(
    cli: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert cli("definition", "--stdin") == (0, [])


def test_invalid_query_exits_with_2_and_prints_nothing(
    cli: Any, capfd: pytest.CaptureFixture[str]
) -> None:
    code = app(
        ["definition", "nonsense"], exit_on_error=False, result_action="return_value"
    )
    captured = capfd.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "PATH:LINE:COLUMN" in captured.err


def test_symbols_and_symbol_take_paths(cli: Any) -> None:
    code, out = cli("symbols", str(MODELS))
    assert code == 0
    assert "make_item" in [s["name"] for s in out[0]["result"]]
    code, out = cli("symbol", f"{MODELS}:make_item")
    target = find(MODELS, "make_item")
    assert out[0]["result"] == [
        {"path": str(MODELS), "line": target.line, "column": target.column}
    ]


def test_server_log_goes_to_the_stderr_file(cli: Any, tmp_path: Path) -> None:
    log = tmp_path / "ty.log"
    code, _ = cli("definition", at(find(APP, "make_item(")), "--ty-stderr", str(log))
    assert code == 0
    assert "Server shut down" in log.read_text()


def test_server_log_is_discarded_by_default(
    capfd: pytest.CaptureFixture[str],
) -> None:
    query = at(find(APP, "make_item("))
    app(
        ["definition", query, "--root", str(PROJECT)],
        exit_on_error=False,
        result_action="return_value",
    )
    assert capfd.readouterr().err == ""


def test_all_flag_selects_indirect_callers(cli: Any) -> None:
    leaf = at(find(PROJECT / "shop" / "graph.py", "leaf()"))
    _, direct = cli("callers", leaf)
    _, indirect = cli("callers", leaf, "--all")
    assert len(indirect[0]["result"]) > len(direct[0]["result"])
    _, limited = cli("callers", leaf, "--max-depth", "1")
    assert limited == direct


def test_stdin_is_not_read_unless_asked(
    capfd: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(at(find(APP, "make_item(")) + "\n"))
    code = app(["definition"], exit_on_error=False, result_action="return_value")
    captured = capfd.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "--stdin" in captured.err


def test_missing_file_is_reported_for_that_query_only(cli: Any) -> None:
    use = at(find(APP, "make_item("))
    code, out = cli("definition", f"{PROJECT}/nope.py:1:1", use)
    assert code == 1
    assert out[0] == {
        "query": {
            "raw": f"{PROJECT}/nope.py:1:1",
            "parsed": {"path": f"{PROJECT}/nope.py", "line": 1, "column": 1},
        },
        "error": f"file not found: {PROJECT}/nope.py",
    }
    assert "result" in out[1]


def test_symbol_queries_are_parsed_too(cli: Any) -> None:
    _, out = cli("symbol", f"{MODELS}:Item.label")
    assert out[0]["query"]["parsed"] == {"path": str(MODELS), "name": "Item.label"}
    _, out = cli("symbols", str(MODELS))
    assert out[0]["query"]["parsed"] == str(MODELS)


def test_install_claude_skill(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    def install(*args: str) -> int:
        return app(
            ["install-claude-skill", "--skills-dir", str(tmp_path), *args],
            exit_on_error=False,
            result_action="return_value",
        )

    assert install() == 0
    skill = tmp_path / "ty-lsp" / "SKILL.md"
    assert skill.read_text().startswith("---\nname: ty-lsp\n")
    skill.write_text("changed")
    assert install("--force") == 0
    assert skill.read_text().startswith("---\nname: ty-lsp\n")


def test_install_claude_skill_asks_before_overwriting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill = tmp_path / "ty-lsp" / "SKILL.md"
    skill.parent.mkdir()
    skill.write_text("mine")
    monkeypatch.setattr("builtins.input", lambda _: "n")
    code = app(
        ["install-claude-skill", "-d", str(tmp_path)],
        exit_on_error=False,
        result_action="return_value",
    )
    assert code == 1
    assert skill.read_text() == "mine"


def test_text_format(
    cli: Any, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(PROJECT)
    leaf = find(PROJECT / "shop" / "graph.py", "leaf()")
    nope = PROJECT / "nope.py"
    code = app(
        [
            "callers",
            at(leaf),
            "--all",
            f"{nope}:1:1",
            "-f",
            "text",
            "--root",
            str(PROJECT),
        ],
        exit_on_error=False,
        result_action="return_value",
    )
    assert code == 1
    out = capfd.readouterr().out
    assert out.startswith(f"## {at(leaf)}\n")
    assert (
        "mid_a shop/graph.py:7:5 calls shop/graph.py:4:5 at shop/graph.py:8:5\n" in out
    )
    assert f"## {nope}:1:1\nerror: file not found: {nope}" in out


def test_text_format_marks_empty_results(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(PROJECT)
    top = at(find(PROJECT / "shop" / "graph.py", "top()"))
    app(
        ["callers", top, "-f", "text", "--root", str(PROJECT)],
        exit_on_error=False,
        result_action="return_value",
    )
    assert capfd.readouterr().out == f"## {top}\n(none)\n"
