"""The ``ty-lsp`` command line: one command per query, many queries per run.

Queries come from the command line, from ``--file`` and from stdin with ``--stdin``
(any mix of them). The output is a JSON list on stdout with one entry per query,
in order::

    {"query": {"raw": "src/a.py:3:5", "parsed": {...}}, "result": [...]}
    {"query": {"raw": "src/a.py:3:5", "parsed": {...}}, "error": "..."}

``raw`` is the query as given, and ``parsed`` is how it was understood, such as
``{"path": ..., "line": 3, "column": 5}``.

The exit code is 1 if any query failed, and 2 if the input is invalid.
"""

import dataclasses
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Annotated, Any

import cyclopts
import pydantic

from ._common import Error, Location, Result
from ._queries._calls._find_callees import find_all_callees, find_direct_callees
from ._queries._calls._find_callers import find_all_callers, find_direct_callers
from ._queries._definitions._find_definition import find_definition
from ._queries._definitions._find_type_definition import find_type_definition
from ._queries._references._find_references import find_references
from ._queries._symbols._find_symbol import SymbolQuery, find_symbol
from ._queries._symbols._list_symbols import list_symbols
from ._queries._types._find_subtypes import find_all_subtypes, find_direct_subtypes
from ._queries._types._find_supertypes import (
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


@cyclopts.Parameter(name="*")
@dataclasses.dataclass(frozen=True)
class Options:
    """Options shared by all commands."""

    file: Path | None = None
    """Also read queries from this file, one per line. Blank lines and lines starting with '#' are skipped."""

    stdin: bool = False
    """Also read queries from stdin, one per line (as for --file)."""

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


def _run[Q](
    args: Sequence[str],
    options: Options,
    parse: Callable[[str], Q],
    query: Callable[[TyLSP, Q], Result[Any]],
) -> int:
    """Run ``query`` for each input and print the JSON list. Returns the exit code."""
    try:
        texts = _read_queries(args, options)
        parsed = [parse(text) for text in texts]
    except (InputError, OSError) as exc:
        print(f"ty-lsp: {exc}", file=sys.stderr)
        return 2
    entries: list[dict[str, Any]] = []
    if parsed:
        with TyLSP(options.root, stderr=options.ty_stderr) as lsp:
            for text, q in zip(texts, parsed, strict=True):
                entry: dict[str, Any] = {
                    "query": {
                        "raw": text,
                        "parsed": _JSON.dump_python(q, mode="json"),
                    },
                }
                result = query(lsp, q)
                if isinstance(result, Error):
                    entry["error"] = result.message
                else:
                    entry["result"] = _JSON.dump_python(result, mode="json")
                entries.append(entry)
    json.dump(entries, sys.stdout, indent=2)
    print()
    return int(any("error" in entry for entry in entries))


@app.command
def definition(*queries: str, options: Options = _DEFAULT_OPTIONS) -> int:
    """Where each name is defined.

    Parameters
    ----------
    queries
        PATH:LINE:COLUMN (1-based) of a name.
    """
    return _run(queries, options, parse_location, find_definition)


@app.command
def type_definition(*queries: str, options: Options = _DEFAULT_OPTIONS) -> int:
    """Where the type of each name or expression is defined.

    Parameters
    ----------
    queries
        PATH:LINE:COLUMN (1-based) of a name or expression.
    """
    return _run(queries, options, parse_location, find_type_definition)


@app.command
def references(*queries: str, options: Options = _DEFAULT_OPTIONS) -> int:
    """Every reference to each name, except its definition.

    Parameters
    ----------
    queries
        PATH:LINE:COLUMN (1-based) of a definition or usage.
    """
    return _run(queries, options, parse_location, find_references)


@app.command
def symbols(*queries: str, options: Options = _DEFAULT_OPTIONS) -> int:
    """Every symbol defined in each file.

    Parameters
    ----------
    queries
        PATH of a Python file.
    """
    return _run(queries, options, parse_path, list_symbols)


@app.command
def symbol(*queries: str, options: Options = _DEFAULT_OPTIONS) -> int:
    """Where each named symbol is defined in its file.

    Parameters
    ----------
    queries
        PATH:NAME, where NAME may be dotted (Class.method).
    """
    return _run(queries, options, parse_symbol, find_symbol)


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
        PATH:LINE:COLUMN (1-based) of a definition or usage.
    all
        Include indirect callers (callers of callers).
    max_depth
        Follow at most this many levels of callers. Implies --all.
    """
    if all or max_depth is not None:
        return _run(
            queries,
            options,
            parse_location,
            lambda lsp, q: find_all_callers(lsp, q, max_depth=max_depth),
        )
    return _run(queries, options, parse_location, find_direct_callers)


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
        PATH:LINE:COLUMN (1-based) of a definition or usage.
    all
        Include indirect callees (what the callees call).
    max_depth
        Follow at most this many levels of callees. Implies --all.
    within
        Look up the callees of callees only inside this directory. Implies --all.
    """
    if all or max_depth is not None or within is not None:
        return _run(
            queries,
            options,
            parse_location,
            lambda lsp, q: find_all_callees(lsp, q, max_depth=max_depth, within=within),
        )
    return _run(queries, options, parse_location, find_direct_callees)


@app.command
def subtypes(
    *queries: str,
    all: bool = False,
    max_depth: int | None = None,
    options: Options = _DEFAULT_OPTIONS,
) -> int:
    """The classes that inherit from each class.

    Parameters
    ----------
    queries
        PATH:LINE:COLUMN (1-based) of a class, or of a name whose type is a class.
    all
        Include indirect subtypes (subtypes of subtypes).
    max_depth
        Follow at most this many levels of subtypes. Implies --all.
    """
    if all or max_depth is not None:
        return _run(
            queries,
            options,
            parse_location,
            lambda lsp, q: find_all_subtypes(lsp, q, max_depth=max_depth),
        )
    return _run(queries, options, parse_location, find_direct_subtypes)


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
        PATH:LINE:COLUMN (1-based) of a class, or of a name whose type is a class.
    all
        Include indirect supertypes (base classes of base classes).
    max_depth
        Follow at most this many levels of supertypes. Implies --all.
    """
    if all or max_depth is not None:
        return _run(
            queries,
            options,
            parse_location,
            lambda lsp, q: find_all_supertypes(lsp, q, max_depth=max_depth),
        )
    return _run(queries, options, parse_location, find_direct_supertypes)


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
