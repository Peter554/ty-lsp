# ty-lsp

Query Python code with [ty](https://github.com/astral-sh/ty)'s language server, from
the command line or from Python. It answers questions like "where is this defined?",
"who calls this?" and "what inherits from this class?". ty is bundled, so there is
nothing else to install. Requires Python 3.13.

Positions are `PATH:LINE:COLUMN`, with 1-based lines and columns, pointing at a name
(its definition or any usage).

## CLI

```console
$ ty-lsp callers src/shop/pricing.py:12:5 --all
```

One command per query. Each takes any number of queries as arguments, and can also
read them from `--file FILE` or, with `--stdin`, from stdin (one per line; blank lines
and `#` comments are skipped). These can be combined.

The output is a JSON list on stdout with one entry per query, in order:

```json
[
  {
    "query": {
      "raw": "src/shop/app.py:6:12",
      "parsed": {"path": "src/shop/app.py", "line": 6, "column": 12}
    },
    "result": [{"path": "src/shop/models.py", "line": 9, "column": 5}]
  }
]
```

A query that fails has `"error": "..."` instead of `"result"`. The exit code is 1 if
any query failed and 2 if the input is invalid.

With `--format text` (`-f text`) the output is compact text instead, better for agents:
a `## query` heading per query, then a line per result, with paths relative to the
current directory.

```console
$ ty-lsp callers src/shop/graph.py:4:5 --all -f text
## src/shop/graph.py:4:5
mid_a src/shop/graph.py:7:5 calls src/shop/graph.py:4:5 at src/shop/graph.py:8:5
top src/shop/graph.py:15:5 calls src/shop/graph.py:7:5 at src/shop/graph.py:16:5
```

A failed query prints `error: ...` and an empty one prints `(none)`.

Options for all commands:

| Option         | Meaning                                                  |
| -------------- | -------------------------------------------------------- |
| `--root DIR`   | The project directory (default: the current directory)   |
| `--format`, `-f` | `json` (default) or `text`                             |
| `--file FILE`  | Also read queries from a file                            |
| `--stdin`      | Also read queries from stdin                             |
| `--ty-stderr FILE` | Write ty's log to a file (default: discarded)        |

### `definition`

Where each name is defined.

```console
$ ty-lsp definition src/shop/app.py:6:12
```

### `type-definition`

Where the type of each name or expression is defined (the class, not the variable).

```console
$ ty-lsp type-definition src/shop/app.py:7:5
```

### `references`

Every reference to each name except its definition: calls, other uses, annotations and
imports.

```console
$ ty-lsp references src/shop/models.py:9:5
```

### `symbols`

Every symbol (function, class, method, variable) defined in each file. Takes file
paths, not positions.

```console
$ ty-lsp symbols src/shop/models.py
```

### `symbol`

Where a named symbol is defined in a file. Takes `PATH:NAME`; use dots for nested
names.

```console
$ ty-lsp symbol src/shop/models.py:Item.label
```

### `callers`

The functions, methods and classes that call each name, with the call sites.

```console
$ ty-lsp callers src/shop/pricing.py:12:5
```

### `callees`

What each function, method or class calls, with the call sites.

```console
$ ty-lsp callees src/shop/checkout.py:20:5
```

### `subtypes`

The classes that inherit from each class.

```console
$ ty-lsp subtypes src/shop/shapes.py:5:7 --all
```

### `supertypes`

The base classes of each class, including `object`.

```console
$ ty-lsp supertypes src/shop/shapes.py:12:7
```

`callers`, `callees`, `subtypes` and `supertypes` return direct relations only. Add
`--all` for indirect ones too, or `--max-depth N` to follow N levels (implies `--all`).
`callees` also takes `--within DIR`: callees outside it are listed, but what they call
is not followed (implies `--all`).

## Claude Code

A skill that teaches [Claude Code](https://claude.com/claude-code) to use the CLI:

```console
$ ty-lsp install-claude-skill
```

This installs it to `~/.claude/skills/ty-lsp/`. Use `--skills-dir` to choose another
directory, and `--force` to overwrite an existing installation without asking.

## Python API

See the [documentation](https://peter554.github.io/ty-lsp/ty_lsp.html).
