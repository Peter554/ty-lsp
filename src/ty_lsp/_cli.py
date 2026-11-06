"""The ``ty-lsp`` command line: one command per query, many queries per run.

Queries come from the command line, from ``--file`` and from stdin with ``--stdin``
(any mix of them). The output is a JSON list on stdout with one entry per query,
in order::

    {"query": {"raw": "src/a.py:3:5", "parsed": {...}}, "result": [...]}
    {"query": {"raw": "src/a.py:3:5", "parsed": {...}}, "error": "..."}

``raw`` is the query as given, and ``parsed`` is how it was understood, such as
``{"path": ..., "line": 3, "column": 5}``.

With ``--format text`` the output is compact text for agents instead: a
``## query`` heading per query, then a line per result (``error: ...`` if it failed,
``(none)`` if empty). The exit code is the same.

Where a query takes a position (``PATH:LINE:COLUMN``) it can take ``PATH:NAME``
instead, such as ``src/a.py:Class.method``. The name must be defined exactly once in
the file: no match, or several, is an error for that query only.

The exit code is 1 if any query failed, and 2 if the input is invalid.
"""

import dataclasses
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Annotated, Any, Literal

import cyclopts
import pydantic

from ._common import Error, Location, Result
from ._queries._calls._build_call_graph import build_call_graph
from ._queries._calls._common import Callee
from ._queries._calls._find_callees import find_all_callees
from ._queries._calls._find_callers import (
    Caller,
    find_all_callers,
    find_direct_callers,
)
from ._queries._definitions._find_definition import find_definition
from ._queries._definitions._find_type_definition import find_type_definition
from ._queries._references._find_references import find_references
from ._queries._symbols._find_symbol import SymbolQuery, find_symbol
from ._queries._symbols._list_symbols import Symbol, list_symbols
from ._queries._types._find_subtypes import (
    Subtype,
    find_all_subtypes,
    find_direct_subtypes,
)
from ._queries._types._find_supertypes import (
    Supertype,
    find_all_supertypes,
    find_direct_supertypes,
)
from ._ty_lsp import TyLSP

app = cyclopts.App(
    name="ty-lsp",
    help="Query Python code with ty's language server.",
    help_format="plaintext",
)

_JSON = pydantic.TypeAdapter[Any](Any)


class InputError(Exception):
    """A query that is not in the expected format."""


def parse_location(text: str) -> Location:
    """Parse ``path:line:column`` (the path may itself contain colons)."""
    path, _, rest = text.strip().rpartition(":")
    path, _, line = path.rpartition(":")
    if not path or not line.isdecimal() or not rest.isdecimal():
        raise InputError(f"expected PATH:LINE:COLUMN, got {text!r}")
    return Location(path=Path(path), line=int(line), column=int(rest))


def parse_path(text: str) -> Path:
    """Parse a file path."""
    return Path(text.strip())


def parse_symbol(text: str) -> SymbolQuery:
    """Parse ``path:name``, where the name may be dotted (``Class.method``)."""
    path, _, name = text.strip().rpartition(":")
    if not path or not name:
        raise InputError(f"expected PATH:NAME, got {text!r}")
    return SymbolQuery(path=Path(path), name=name)


def parse_target(text: str) -> Location | SymbolQuery:
    """Parse ``path:line:column``, or ``path:name`` (a name is never all digits)."""
    try:
        head, _, last = text.strip().rpartition(":")
        if last.isdecimal():
            return parse_location(text)
        if head and all(part.isidentifier() for part in last.split(".")):
            return parse_symbol(text)
    except InputError:
        pass
    raise InputError(f"expected PATH:LINE:COLUMN or PATH:NAME, got {text!r}")


def resolve_target(lsp: TyLSP, target: Location | SymbolQuery) -> Result[Location]:
    """The position of ``target``; a name must be defined exactly once in its file."""
    if isinstance(target, Location):
        return target
    found = find_symbol(lsp, target)
    if isinstance(found, Error):
        return found
    where = f"{target.path}:{target.name}"
    if not found:
        message = f"symbol not found: {where}"
    elif len(found) > 1:
        message = f"ambiguous symbol {where}, defined at: " + ", ".join(
            f"{loc.line}:{loc.column}" for loc in found
        )
    else:
        return found[0]
    return Error(message, LookupError(message))


def _callees_many(
    lsp: TyLSP, queries: Sequence[Location], max_depth: int | None, within: Path | None
) -> list[Result[Any]]:
    """The callees of each query, from one call graph (which is much faster)."""
    graph = build_call_graph(lsp, queries, max_depth=max_depth, within=within)
    if isinstance(graph, Error):
        # One of the queries failed (such as a file that does not exist). Ask one by
        # one, to find which, and to still answer the others.
        return [
            find_all_callees(lsp, q, max_depth=max_depth, within=within)
            for q in queries
        ]
    return [graph.callees_of(q) for q in queries]


def _identity[Q](lsp: TyLSP, query: Q) -> Q:
    return query


@cyclopts.Parameter(name="*")
@dataclasses.dataclass(frozen=True)
class Options:
    """Options shared by all commands."""

    file: Path | None = None
    """Also read queries from this file, one per line. Blank lines and lines starting with '#' are skipped."""

    stdin: bool = False
    """Also read queries from stdin, one per line (as for --file)."""

    format: Annotated[
        Literal["json", "text"], cyclopts.Parameter(name=["--format", "-f"])
    ] = "json"
    """The output format: 'json', or 'text' (compact, for reading by agents)."""

    root: Path = Path()
    """The project directory the server runs in."""

    ty_stderr: Path | None = None
    """Write the server's stderr (its log) to this file. Discarded by default."""


_DEFAULT_OPTIONS = Options()


def _read_queries(args: Sequence[str], options: Options) -> list[str]:
    """The queries from ``args``, ``options.file`` and (if asked) stdin."""
    if not args and options.file is None and not options.stdin:
        raise InputError(
            "no queries: give them as arguments, with --file or with --stdin"
        )

    def lines(text: str) -> list[str]:
        stripped = (line.strip() for line in text.splitlines())
        return [line for line in stripped if line and not line.startswith("#")]

    queries = list(args)
    if options.file is not None:
        queries += lines(options.file.read_text())
    if options.stdin:
        queries += lines(sys.stdin.read())
    return queries


def _text_line(item: object) -> str:
    """One result as a line of text. Paths are relative to the cwd where possible."""

    def at(location: Location) -> str:
        try:
            path = location.path.relative_to(Path.cwd())
        except ValueError:
            path = location.path
        return f"{path}:{location.line}:{location.column}"

    def sites(call_sites: Sequence[Location]) -> str:
        return " at " + ", ".join(map(at, call_sites)) if call_sites else ""

    match item:
        case Location():
            return at(item)
        case Caller():
            return f"{item.name} {at(item.location)} calls {at(item.callee)}{sites(item.call_sites)}"
        case Callee():
            return f"{at(item.caller)} calls {item.name} {at(item.location)}{sites(item.call_sites)}"
        case Subtype():
            return f"{item.name} {at(item.location)} subtype of {at(item.supertype)}"
        case Supertype():
            return f"{item.name} {at(item.location)} supertype of {at(item.subtype)}"
        case Symbol():
            return f"{item.name} {at(item.location)}"
        case _:
            raise TypeError(f"cannot render {item!r}")


def _render_text(outcomes: Sequence[tuple[str, Result[Any]]]) -> str:
    """The outcomes as text: a ``## query`` heading, then a line per result."""
    blocks: list[str] = []
    for text, result in outcomes:
        if isinstance(result, Error):
            lines = [f"error: {result.message}"]
        else:
            lines = [_text_line(item) for item in result] or ["(none)"]
        blocks.append("\n".join([f"## {text}", *lines]))
    return "\n\n".join(blocks)


def _render_json(outcomes: Sequence[tuple[str, Any, Result[Any]]]) -> str:
    """The outcomes as a JSON list with an entry per query."""
    entries: list[dict[str, Any]] = []
    for text, parsed, result in outcomes:
        entry: dict[str, Any] = {
            "query": {"raw": text, "parsed": _JSON.dump_python(parsed, mode="json")}
        }
        if isinstance(result, Error):
            entry["error"] = result.message
        else:
            entry["result"] = _JSON.dump_python(result, mode="json")
        entries.append(entry)
    return json.dumps(entries, indent=2)


def _run[Q, R](
    args: Sequence[str],
    options: Options,
    parse: Callable[[str], Q],
    resolve: Callable[[TyLSP, Q], Result[R]],
    query: Callable[[TyLSP, R], Result[Any]],
    many: Callable[[TyLSP, Sequence[R]], Sequence[Result[Any]]] | None = None,
) -> int:
    """Run ``query`` for each input and print the output. Returns the exit code.

    The parsed input is turned into the query's input with ``resolve``, which can
    fail for just that input. ``many`` can answer all the (resolved) inputs together,
    if that is faster than one by one. It returns a result for each, in order.
    """
    try:
        texts = _read_queries(args, options)
        parsed = [parse(text) for text in texts]
    except (InputError, OSError) as exc:
        print(f"ty-lsp: {exc}", file=sys.stderr)
        return 2
    outcomes: list[tuple[str, Q | R, Result[Any]]] = []
    if parsed:
        with TyLSP(options.root, stderr=options.ty_stderr) as lsp:
            resolutions = [resolve(lsp, q) for q in parsed]
            ok = [r for r in resolutions if not isinstance(r, Error)]
            answers = iter(many(lsp, ok) if many else [query(lsp, r) for r in ok])
            for text, q, resolved in zip(texts, parsed, resolutions, strict=True):
                if isinstance(resolved, Error):
                    outcomes.append((text, q, resolved))
                else:
                    outcomes.append((text, resolved, next(answers)))
    if options.format == "text":
        print(_render_text([(text, result) for text, _, result in outcomes]))
    else:
        print(_render_json(outcomes))
    return int(any(isinstance(result, Error) for _, _, result in outcomes))


@app.command
def definition(*queries: str, options: Options = _DEFAULT_OPTIONS) -> int:
    """Where each name is defined.

    Parameters
    ----------
    queries
        PATH:LINE:COLUMN (1-based) or PATH:NAME of a name.
    """
    return _run(queries, options, parse_target, resolve_target, find_definition)


@app.command
def type_definition(*queries: str, options: Options = _DEFAULT_OPTIONS) -> int:
    """Where the type of each name or expression is defined.

    Parameters
    ----------
    queries
        PATH:LINE:COLUMN (1-based) or PATH:NAME of a name or expression.
    """
    return _run(queries, options, parse_target, resolve_target, find_type_definition)


@app.command
def references(*queries: str, options: Options = _DEFAULT_OPTIONS) -> int:
    """Every reference to each name, except its definition.

    Parameters
    ----------
    queries
        PATH:LINE:COLUMN (1-based) or PATH:NAME of a definition or usage.
    """
    return _run(queries, options, parse_target, resolve_target, find_references)


@app.command
def symbols(*queries: str, options: Options = _DEFAULT_OPTIONS) -> int:
    """Every symbol defined in each file.

    Parameters
    ----------
    queries
        PATH of a Python file.
    """
    return _run(queries, options, parse_path, _identity, list_symbols)


@app.command
def symbol(*queries: str, options: Options = _DEFAULT_OPTIONS) -> int:
    """Where each named symbol is defined in its file.

    Parameters
    ----------
    queries
        PATH:NAME, where NAME may be dotted (Class.method).
    """
    return _run(queries, options, parse_symbol, _identity, find_symbol)


@app.command
def callers(
    *queries: str,
    all: bool = False,
    max_depth: int | None = None,
    options: Options = _DEFAULT_OPTIONS,
) -> int:
    """The functions, methods and classes that call each name.

    Parameters
    ----------
    queries
        PATH:LINE:COLUMN (1-based) or PATH:NAME of a definition or usage.
    all
        Include indirect callers (callers of callers).
    max_depth
        Follow at most this many levels of callers. Implies --all.
    """
    if all or max_depth is not None:
        return _run(
            queries,
            options,
            parse_target,
            resolve_target,
            lambda lsp, q: find_all_callers(lsp, q, max_depth=max_depth),
        )
    return _run(queries, options, parse_target, resolve_target, find_direct_callers)


@app.command
def callees(
    *queries: str,
    all: bool = False,
    max_depth: int | None = None,
    within: Path | None = None,
    options: Options = _DEFAULT_OPTIONS,
) -> int:
    """What each function, method or class calls.

    Parameters
    ----------
    queries
        PATH:LINE:COLUMN (1-based) or PATH:NAME of a definition or usage.
    all
        Include indirect callees (what the callees call).
    max_depth
        Follow at most this many levels of callees. Implies --all.
    within
        Look up the callees of callees only inside this directory. Implies --all.
    """
    if not (all or max_depth is not None or within is not None):
        max_depth = 1
    return _run(
        queries,
        options,
        parse_target,
        resolve_target,
        lambda lsp, q: find_all_callees(lsp, q, max_depth=max_depth, within=within),
        many=lambda lsp, qs: _callees_many(lsp, qs, max_depth, within),
    )


@app.command
def subtypes(
    *queries: str,
    all: bool = False,
    max_depth: int | None = None,
    options: Options = _DEFAULT_OPTIONS,
) -> int:
    """The classes in the project that inherit from each class.

    Parameters
    ----------
    queries
        PATH:LINE:COLUMN (1-based) or PATH:NAME of a class, or of a name whose type is a class.
    all
        Include indirect subtypes (subtypes of subtypes).
    max_depth
        Follow at most this many levels of subtypes. Implies --all.
    """
    if all or max_depth is not None:
        return _run(
            queries,
            options,
            parse_target,
            resolve_target,
            lambda lsp, q: find_all_subtypes(lsp, q, max_depth=max_depth),
        )
    return _run(queries, options, parse_target, resolve_target, find_direct_subtypes)


@app.command
def supertypes(
    *queries: str,
    all: bool = False,
    max_depth: int | None = None,
    options: Options = _DEFAULT_OPTIONS,
) -> int:
    """The base classes of each class.

    Parameters
    ----------
    queries
        PATH:LINE:COLUMN (1-based) or PATH:NAME of a class, or of a name whose type is a class.
    all
        Include indirect supertypes (base classes of base classes).
    max_depth
        Follow at most this many levels of supertypes. Implies --all.
    """
    if all or max_depth is not None:
        return _run(
            queries,
            options,
            parse_target,
            resolve_target,
            lambda lsp, q: find_all_supertypes(lsp, q, max_depth=max_depth),
        )
    return _run(queries, options, parse_target, resolve_target, find_direct_supertypes)


_DEFAULT_SKILLS_DIR = Path.home() / ".claude" / "skills"


@app.command(name="install-claude-skill")
def install_claude_skill(
    *,
    skills_dir: Annotated[
        Path, cyclopts.Parameter(name=["--skills-dir", "-d"])
    ] = _DEFAULT_SKILLS_DIR,
    force: Annotated[
        bool, cyclopts.Parameter(name=["--force", "-f"], negative=())
    ] = False,
) -> int:
    """Install the ty-lsp skill for Claude Code.

    Parameters
    ----------
    skills_dir
        The directory where Claude skills are stored.
    force
        Overwrite an existing installation without asking.
    """
    source = Path(__file__).parent / "claude_skill" / "SKILL.md"
    target = skills_dir / "ty-lsp" / "SKILL.md"
    if target.exists() and not force:
        answer = input(f"Skill already exists at {target}. Overwrite? [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            print("Installation cancelled.")
            return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text())
    print(f"Installed skill to {target}")
    return 0


def main() -> None:
    """The ``ty-lsp`` entry point."""
    sys.exit(app())
