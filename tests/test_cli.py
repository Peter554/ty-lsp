"""Tests of the ``ty-lsp`` command line against ``tests/fixture_project``."""

import io
import json
from pathlib import Path
from typing import Any

import pytest

from ty_lsp._cli import _relativise, app

from ._support import PROJECT, find

APP = PROJECT / "shop" / "app.py"
MODELS = PROJECT / "shop" / "models.py"
INVENTORY = PROJECT / "shop" / "inventory"


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


def rel(path: Path) -> str:
    """``path`` as the CLI prints it: relative to the cwd."""
    return str(path.relative_to(Path.cwd()))


def at(location: Any) -> str:
    return f"{location.path}:{location.line}:{location.column}"


def test_queries_from_arguments_give_one_entry_each(cli: Any) -> None:
    use = find(APP, "make_item(")
    code, out = cli("definition", at(use), at(find(APP, "item.label()")))
    target = find(MODELS, "make_item")
    assert code == 0
    assert [e["query"]["raw"] for e in out] == [at(use), at(find(APP, "item.label()"))]
    assert out[0]["query"]["parsed"] == {
        "path": rel(use.path),
        "line": use.line,
        "column": use.column,
    }
    assert out[0]["result"] == [
        {"path": rel(MODELS), "line": target.line, "column": target.column}
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
        {"path": rel(MODELS), "line": target.line, "column": target.column}
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
            "parsed": {"path": rel(PROJECT / "nope.py"), "line": 1, "column": 1},
        },
        "error": f"file not found: {PROJECT}/nope.py",
    }
    assert "result" in out[1]


def test_symbol_queries_are_parsed_too(cli: Any) -> None:
    _, out = cli("symbol", f"{MODELS}:Item.label")
    assert out[0]["query"]["parsed"] == {"path": rel(MODELS), "name": "Item.label"}
    _, out = cli("symbols", str(MODELS))
    assert out[0]["query"]["parsed"] == rel(MODELS)


def test_install_claude_skill_is_a_stub_that_runs_claude_skill_instructions(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    def run(*args: str) -> int:
        return app(args, exit_on_error=False, result_action="return_value")

    skill = tmp_path / "ty-lsp" / "SKILL.md"
    assert run("install-claude-skill", "-d", str(tmp_path)) == 0
    stub = skill.read_text()
    assert stub.startswith("---\nname: ty-lsp\ndescription: ")
    assert "\nallowed-tools: Bash(ty-lsp *)\n---\n\n!`ty-lsp claude-skill`\n" in stub
    assert "# ty-lsp" not in stub  # the instructions are not in the stub

    skill.write_text("changed")
    assert run("install-claude-skill", "-d", str(tmp_path), "--force") == 0
    assert skill.read_text() == stub

    capfd.readouterr()
    run("claude-skill")
    instructions = capfd.readouterr().out
    assert instructions.startswith("# ty-lsp\n")
    assert "---" not in instructions.splitlines()[0]
    assert "name: ty-lsp" not in instructions


def test_install_claude_skill_with_another_command(tmp_path: Path) -> None:
    app(
        ["install-claude-skill", "-d", str(tmp_path), "--command", "uvx ty-lsp"],
        exit_on_error=False,
        result_action="return_value",
    )
    stub = (tmp_path / "ty-lsp" / "SKILL.md").read_text()
    assert "allowed-tools: Bash(uvx ty-lsp *)" in stub
    assert stub.endswith("\n!`uvx ty-lsp claude-skill`\n")


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


def test_a_name_resolves_to_its_position(cli: Any) -> None:
    graph = PROJECT / "shop" / "graph.py"
    leaf = find(graph, "leaf()")
    _, by_position = cli("callers", at(leaf))
    code, by_name = cli("callers", f"{graph}:leaf")
    assert code == 0
    assert by_name[0]["result"] == by_position[0]["result"]
    assert by_name[0]["query"] == {
        "raw": f"{graph}:leaf",
        "parsed": {"path": rel(graph), "line": leaf.line, "column": leaf.column},
    }


def test_a_missing_or_ambiguous_name_is_an_error_for_that_query_only(cli: Any) -> None:
    branches = PROJECT / "shop" / "branches.py"
    first = find(branches, "def pick", nth=1)
    second = find(branches, "def pick", nth=2)
    use = at(find(APP, "make_item("))
    code, out = cli("definition", f"{branches}:pick", f"{branches}:nope", use)
    assert code == 1
    assert out[0]["error"] == (
        f"ambiguous symbol {branches}:pick, defined at: "
        f"{first.line}:{first.column + 4}, {second.line}:{second.column + 4}"
    )
    assert out[1]["error"] == f"symbol not found: {branches}:nope"
    assert "result" in out[2]


def test_a_position_must_have_a_column(
    capfd: pytest.CaptureFixture[str],
) -> None:
    code = app(
        ["definition", f"{APP}:6"], exit_on_error=False, result_action="return_value"
    )
    assert code == 2
    assert "PATH:LINE:COLUMN or PATH:NAME" in capfd.readouterr().err


def test_callees_of_many_queries_use_one_call_graph_and_keep_errors_per_query(
    cli: Any,
) -> None:
    graph = PROJECT / "shop" / "graph.py"
    top, leaf = at(find(graph, "top()")), at(find(graph, "leaf()"))
    nope = f"{PROJECT}/nope.py:1:1"
    code, out = cli("callees", top, nope, leaf, "--all")
    assert code == 1
    assert out[1]["error"] == f"file not found: {PROJECT}/nope.py"
    # The others are the same as asking for each alone.
    for entry, query in ((out[0], top), (out[2], leaf)):
        _, alone = cli("callees", query, "--all")
        assert entry["result"] == alone[0]["result"]
    assert len(out[0]["result"]) == 4


def test_callees_without_all_are_direct_only(cli: Any) -> None:
    top = at(find(PROJECT / "shop" / "graph.py", "top()"))
    _, direct = cli("callees", top)
    _, depth_one = cli("callees", top, "--max-depth", "1")
    _, everything = cli("callees", top, "--all")
    assert direct == depth_one
    assert len(direct[0]["result"]) == 2 < len(everything[0]["result"])


def test_dotted_module_paths_are_looked_up(cli: Any) -> None:
    graph = PROJECT / "shop" / "graph.py"
    leaf = find(graph, "leaf()")
    _, by_file = cli("callers", f"{graph}:leaf")
    code, by_module = cli("callers", "shop.graph:leaf")
    assert code == 0
    assert by_module[0]["result"] == by_file[0]["result"]
    assert by_module[0]["query"] == {
        "raw": "shop.graph:leaf",
        "parsed": {"path": rel(graph), "line": leaf.line, "column": leaf.column},
    }


def test_dotted_module_paths_for_every_kind_of_query(cli: Any) -> None:
    models = PROJECT / "shop" / "models.py"
    use = find(models, "make_item")
    _, out = cli("symbol", "shop.models:make_item")
    assert out[0]["result"] == [
        {"path": rel(models), "line": use.line, "column": use.column}
    ]
    _, out = cli("symbols", "shop.models", "shop.inventory")
    assert "make_item" in [s["name"] for s in out[0]["result"]]
    assert out[1]["query"]["raw"] == "shop.inventory"
    _, out = cli(
        "definition",
        f"shop.app:{find(APP, 'make_item(').line}:{find(APP, 'make_item(').column}",
    )
    assert out[0]["result"][0]["path"] == rel(models)


def test_an_unknown_module_is_an_error_for_that_query_only(cli: Any) -> None:
    code, out = cli("symbol", "shop.nope:x", "shop.models:make_item")
    assert code == 1
    assert out[0]["error"] == "module not found: shop.nope"
    assert "result" in out[1]


def test_is_module_path() -> None:
    from ty_lsp._cli import is_module_path

    for module in ("shop", "shop.models", "a.b.c", "models"):
        assert is_module_path(Path(module))
    for file in (
        "shop/models.py",
        "models.py",
        "src/shop",
        "shop.pyi",
        "a-b.c",
    ):
        assert not is_module_path(Path(file))


def test_file_command(cli: Any) -> None:
    code, out = cli("file", "shop.models", "shop", "shop.nope", "src/shop/models.py")
    assert code == 1
    assert out[0]["query"] == {"raw": "shop.models", "parsed": "shop.models"}
    assert out[0]["result"] == [rel(PROJECT / "shop" / "models.py")]
    assert out[1]["result"] == [rel(PROJECT / "shop" / "__init__.py")]
    assert out[2]["error"] == "module not found: shop.nope"
    assert out[3]["error"] == "not a dotted module path: 'src/shop/models.py'"


def test_file_command_text_output(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(PROJECT)
    app(
        ["file", "shop.models", "-f", "text", "--root", str(PROJECT)],
        exit_on_error=False,
        result_action="return_value",
    )
    assert capfd.readouterr().out == "## shop.models\nshop/models.py\n"


def test_decorated_by_command(cli: Any) -> None:
    markers = PROJECT / "shop" / "markers.py"
    internal = find(markers, "def internal")
    internal = internal.model_copy(update={"column": internal.column + len("def ")})
    code, out = cli("decorated-by", at(internal), "shop.markers:internal")
    assert code == 0
    assert out[0]["result"] == out[1]["result"]
    names = [symbol["name"] for symbol in out[0]["result"]]
    assert {"post", "cached", "Archive"} <= set(names)
    assert set(out[0]["result"][0]) == {"name", "location", "start"}


def test_paths_outside_the_cwd_stay_absolute(tmp_path: Path) -> None:
    inside = Path.cwd() / "src" / "a.py"
    data = {"query": [{"path": inside}, (tmp_path / "b.py",)], "n": 1}
    assert _relativise(data) == {
        "query": [{"path": str(Path("src") / "a.py")}, [str(tmp_path / "b.py")]],
        "n": 1,
    }


def test_implementations_command(cli: Any) -> None:
    renderers = PROJECT / "shop" / "renderers.py"
    code, out = cli("implementations", "shop.renderers:Renderer.render")
    assert code == 0
    assert out[0]["result"] == [
        {"path": rel(renderers), "line": line, "column": 9} for line in (2, 7, 12)
    ]


def test_exclude_leaves_out_results_in_each_directory_or_file(cli: Any) -> None:
    query = "shop.inventory.stock:Stock"
    checkout = PROJECT / "shop" / "checkout.py"
    _, out = cli("references", query)
    paths = {r["path"] for r in out[0]["result"]}
    assert rel(checkout) in paths
    assert rel(INVENTORY / "deep" / "report.py") in paths

    _, out = cli("references", query, "--exclude", str(INVENTORY))
    assert {r["path"] for r in out[0]["result"]} == {rel(checkout)}

    _, out = cli(
        "references", query, "--exclude", str(INVENTORY), "--exclude", str(checkout)
    )
    assert out[0]["result"] == []


def test_exclude_matches_whole_names_not_prefixes(cli: Any) -> None:
    query = "shop.inventory.stock:Stock"
    _, out = cli("references", query)
    _, filtered = cli("references", query, "--exclude", f"{INVENTORY}/aud")
    assert filtered == out


def test_exclude_filters_other_kinds_of_result(cli: Any) -> None:
    shapes = PROJECT / "shop" / "shapes.py"
    _, out = cli("subtypes", "shop.shapes:Shape", "--all", "--exclude", str(shapes))
    # Followed through the excluded file: Triangle is a subtype of Polygon there.
    assert [r["name"] for r in out[0]["result"]] == ["Triangle"]


def test_filter_keeps_only_results_in_any_of_the_directories_or_files(
    cli: Any,
) -> None:
    query = "shop.inventory.stock:Stock"
    checkout = PROJECT / "shop" / "checkout.py"
    _, out = cli("references", query, "--filter", str(INVENTORY))
    paths = {r["path"] for r in out[0]["result"]}
    assert paths
    assert all(Path(p).is_relative_to(rel(INVENTORY)) for p in paths)

    _, out = cli(
        "references", query, "--filter", str(INVENTORY), "--filter", str(checkout)
    )
    assert {r["path"] for r in out[0]["result"]} == paths | {rel(checkout)}


def test_filter_with_exclude_keeps_a_directory_except_part_of_it(cli: Any) -> None:
    query = "shop.inventory.stock:Stock"
    deep = INVENTORY / "deep"
    _, out = cli(
        "references", query, "--filter", str(INVENTORY), "--exclude", str(deep)
    )
    paths = {r["path"] for r in out[0]["result"]}
    assert paths
    assert all(Path(p).is_relative_to(rel(INVENTORY)) for p in paths)
    assert not any(Path(p).is_relative_to(rel(deep)) for p in paths)


def test_filter_matches_whole_names_not_prefixes(cli: Any) -> None:
    _, out = cli(
        "references", "shop.inventory.stock:Stock", "--filter", f"{INVENTORY}/aud"
    )
    assert out[0]["result"] == []
