# ty-lsp

Query Python code with [ty](https://github.com/astral-sh/ty)'s language server, from
the command line or from Python. It answers questions like "where is this defined?",
"who calls this?" and "what inherits from this class?". ty is bundled, so there is
nothing else to install. Requires Python >=3.13.

- [CLI](https://github.com/Peter554/ty-lsp#cli)
- [Server](https://github.com/Peter554/ty-lsp#server)
- [Claude Code Skill](https://github.com/Peter554/ty-lsp#claude-code)
- [Python API](https://github.com/Peter554/ty-lsp#python-api)

## Installation

```bash
uv tool install --from git+https://github.com/Peter554/ty-lsp ty-lsp
```

To use it as a Python library, add it to a project instead:
`uv add git+https://github.com/Peter554/ty-lsp`.

## CLI

```console
$ ty-lsp callers src/shop/pricing.py:12:5 --all
$ ty-lsp callers shop.pricing:total --all -f text
```

There is one command per query (see [Commands](#commands)). Each takes any number of
queries, and runs them all with one ty server, so give it many at once when you can.

### Query Syntax

A query says where to look. It has one of these forms:

| Form               | Meaning                                                                      | Taken by commands                                                                                                       |
| ------------------ | ---------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `PATH:LINE:COLUMN` | A position: the 1-based line and column of a name (a definition or a usage)  | `definition`, `type-definition`, `references`, `decorated-by`, `callers`, `callees`, `subtypes`, `supertypes`           |
| `PATH:NAME`        | A symbol defined in the file: `Item`, or `Item.label` for one inside another | `definition`, `type-definition`, `references`, `decorated-by`, `callers`, `callees`, `subtypes`, `supertypes`, `symbol` |
| `PATH`             | A file                                                                       | `symbols`                                                                                                               |
| `MODULE`           | A dotted module path, such as `shop.models`                                  | `file`                                                                                                                  |

Where `PATH` is either:

- a **file path**, such as `src/shop/models.py`. A relative path is relative to the
  current directory.
- a **dotted module path**, such as `shop.models`, which ty looks up as it would an
  `import`. It gives the module's file (`shop/models.py`), or `__init__.py` for a
  package (`shop`). A file path is anything with a `/` or ending in `.py`.

So these are all the same query:

```console
$ ty-lsp callers src/shop/models.py:Item.label
$ ty-lsp callers shop.models:Item.label
$ ty-lsp callers src/shop/models.py:5:9
```

A name must be defined exactly once in its file. If it isn't found, or is defined
several times (for example in `if`/`else` branches), that query fails with an error
listing the candidates, and you can repeat it with a position.

Queries are given as arguments, and also with `--file FILE` or `--stdin` (one per
line; blank lines and `#` comments are skipped). These can be combined.

### Output

The output is a JSON list on stdout with one entry per query, in order:

```json
[
  {
    "query": {
      "raw": "shop.app:6:12",
      "parsed": { "path": "src/shop/app.py", "line": 6, "column": 12 }
    },
    "result": [{ "path": "src/shop/models.py", "line": 9, "column": 5 }]
  }
]
```

`raw` is the query as given, and `parsed` is the position it was resolved to. Paths in
`parsed` and in the results are relative to the current directory, unless they are
outside it. A query that fails has `"error": "..."` instead of `"result"`. The exit code is 1 if any query
failed and 2 if the input is invalid.

With `--format text` (`-f text`) the output is compact text instead, better for agents:
a `## query` heading per query, then a line per result, with paths relative to the
current directory. A failed query prints `error: ...` and an empty one prints
`(none)`.

```console
$ ty-lsp callers src/shop/graph.py:4:5 --all -f text
## src/shop/graph.py:4:5
mid_a src/shop/graph.py:7:5 calls src/shop/graph.py:4:5 at src/shop/graph.py:8:5
top src/shop/graph.py:15:5 calls src/shop/graph.py:7:5 at src/shop/graph.py:16:5
```

### Common Options

These are taken by all commands:

| Option             | Meaning                                                |
| ------------------ | ------------------------------------------------------ |
| `--root DIR`       | The project directory (default: the current directory) |
| `--format`, `-f`   | `json` (default) or `text`                             |
| `--file FILE`      | Also read queries from a file                          |
| `--stdin`          | Also read queries from stdin                           |
| `--start-server`   | Use the [server](#server), starting one if needed      |
| `--ty-stderr FILE` | Write ty's log to a file (default: discarded)          |

### Commands

#### `definition`

Where each name is defined.

```console
$ ty-lsp definition src/shop/app.py:6:12
```

#### `type-definition`

Where the type of each name or expression is defined (the class, not the variable).

```console
$ ty-lsp type-definition src/shop/app.py:7:5
```

#### `references`

Every reference to each name except its definition: calls, other uses, annotations and
imports.

```console
$ ty-lsp references src/shop/models.py:9:5
```

#### `file`

The file of each module, given a dotted module path. A package gives its
`__init__.py`. The result is a list with the one path, like the other commands.

```console
$ ty-lsp file shop.models
```

#### `symbols`

Every symbol (function, class, method, variable) defined in each file. Takes a `PATH`.

```console
$ ty-lsp symbols src/shop/models.py
$ ty-lsp symbols shop.models
```

#### `symbol`

Where a named symbol is defined in a file. Takes `PATH:NAME`. This gives the position
that the other commands take.

```console
$ ty-lsp symbol src/shop/models.py:Item.label
```

#### `decorated-by`

The functions, methods and classes decorated with each decorator. Give a position on
the decorator's name, where it is defined or used. Decorators are matched by what they
resolve to, so aliases and re-exports count and a different decorator with the same
name does not. The result is each decorated name's position, which the other commands
take.

```console
$ ty-lsp decorated-by src/shop/markers.py:internal
```

A decorator with several definitions (`@overload`) makes `PATH:NAME` ambiguous, so give
a position on one of its usages instead. A decorator that is a variable
(`deco = make_deco()`) finds nothing, because ty does not track calls to variables.

#### `callers`

The functions, methods and classes that call each name, with the call sites.

```console
$ ty-lsp callers src/shop/pricing.py:12:5
```

Options:

- `--all`: also the indirect callers (callers of callers). By default only direct
  callers are returned.
- `--max-depth N`: follow at most N levels of callers (implies `--all`).

#### `callees`

What each function, method or class calls, with the call sites.
Give several queries and they share one call graph: a function below more than one
is looked up only once.

```console
$ ty-lsp callees src/shop/checkout.py:20:5
```

Options:

- `--all`: also the indirect callees (what the callees call). By default only direct
  callees are returned.
- `--max-depth N`: follow at most N levels of callees (implies `--all`).
- `--within DIR`: callees outside the directory are listed, but what they call is not
  followed (implies `--all`).

#### `subtypes`

The classes that inherit from each class. Only subclasses defined in the project are
found, not those in the standard library or installed packages.

```console
$ ty-lsp subtypes src/shop/shapes.py:5:7 --all
```

Options:

- `--all`: also the indirect subtypes (subtypes of subtypes). By default only direct
  subtypes are returned.
- `--max-depth N`: follow at most N levels of subtypes (implies `--all`).

#### `supertypes`

The base classes of each class, including `object`.

```console
$ ty-lsp supertypes src/shop/shapes.py:12:7
```

Options:

- `--all`: also the indirect supertypes (base classes of base classes). By default only
  direct supertypes are returned.
- `--max-depth N`: follow at most N levels of supertypes (implies `--all`).

## Server

Most of the time of a query is ty indexing the project, and each command starts a
new ty server. To pay for that once, keep a server running:

```console
$ ty-lsp serve                  # in a terminal; Ctrl-C (or `ty-lsp stop-server`) to stop it
$ ty-lsp subtypes shop.models:Item -f text      # now ~10x faster after the first query
```

While it runs, every query command in the project (the same `--root`) uses it, and
prints the same output. It picks up edits, new files and deleted files. Each request
is logged to stderr.

With `--start-server`, a command starts a server in the background if there is none,
so nothing needs to be set up first. It stops after 5 minutes without a request
(`ty-lsp serve --idle-timeout MINUTES` sets this for one started by hand), and its
log is `ty-lsp-<uid>/<hash>.log` in the temporary directory. `ty-lsp stop-server` stops it.
`ty-lsp list-servers` lists the running servers (their project, process id, age and requests).

A server uses a lot of memory on a large project (several GB on a big monorepo).

## Claude Code

A skill that teaches [Claude Code](https://claude.com/claude-code) to use the CLI:

```console
$ ty-lsp install-claude-skill
```

This installs it to `~/.claude/skills/ty-lsp/`. Use `--skills-dir` to choose another
directory, and `--force` to overwrite an existing installation without asking.

The installed `SKILL.md` is a small stub: its body is `` !`ty-lsp claude-skill` ``, which
Claude Code runs when the skill is used, to get the instructions. So the instructions
always match the installed `ty-lsp`, and you don't need to install the skill again
after upgrading it. The stub allows that one command (`allowed-tools`), and needs
`ty-lsp` on the `PATH`. If it isn't, for example when you use `uvx`, say how to run it:

```console
$ ty-lsp install-claude-skill --command "uvx --from git+https://github.com/Peter554/ty-lsp ty-lsp"
```

## Python API

See the [documentation](https://peter554.github.io/ty-lsp/ty_lsp.html).
