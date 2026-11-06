---
name: ty-lsp
description: Answers code navigation questions about Python code with ty - where a name is defined, what references it, who calls a function, what a function calls, and a class's subtypes and supertypes. Use instead of grep when you need exact, type-aware results.
---

# ty-lsp

`ty-lsp` queries Python code with ty's language server. Prefer it over grep for questions about definitions, usages, call graphs and class hierarchies: results follow imports, re-exports and inferred types.

Run it from the project root (or pass `--root DIR`). A position is `PATH:LINE:COLUMN` with **1-based** line and column, pointing at a name (a definition or any usage).

## Commands

```bash
ty-lsp definition PATH:LINE:COLUMN        # Where the name is defined
ty-lsp type-definition PATH:LINE:COLUMN   # Where the name's type (class) is defined
ty-lsp references PATH:LINE:COLUMN        # All references, except the definition
ty-lsp symbols PATH                       # Every symbol defined in a file
ty-lsp symbol PATH:NAME                   # Where a symbol is defined, e.g. src/a.py:Class.method
ty-lsp callers PATH:LINE:COLUMN           # Direct callers, with call sites
ty-lsp callers PATH:LINE:COLUMN --all     # Direct and indirect callers
ty-lsp callees PATH:LINE:COLUMN           # What it calls directly, with call sites
ty-lsp callees PATH:LINE:COLUMN --within src   # Indirect callees, only expanding inside src/
ty-lsp subtypes PATH:LINE:COLUMN          # Classes inheriting from a class
ty-lsp supertypes PATH:LINE:COLUMN        # Base classes of a class
```

`callers`, `callees`, `subtypes` and `supertypes` take `--all` (indirect too) and `--max-depth N` (implies `--all`). `callees` also takes `--within DIR` (implies `--all`).

## Tips

- To find a position, use `symbols PATH` or `symbol PATH:NAME`, which give the location of a name.
- Pass several queries in one run - the server starts once: `ty-lsp references a.py:3:5 b.py:8:1`. Or use `--stdin` / `--file FILE` with one query per line.
- Prefer `callers`/`callees` without `--all` first; the indirect graph (especially callees, which include the standard library) can be large. Limit it with `--max-depth` or `--within`.
- Read results with care for empty ones: an empty result means ty found nothing, such as a dynamic call it cannot resolve.

## Output

A JSON list on stdout with one entry per query, in order:

```json
[{"query": {"raw": "src/a.py:3:5", "parsed": {"path": "src/a.py", "line": 3, "column": 5}},
  "result": [{"path": "src/b.py", "line": 9, "column": 5}]}]
```

A query that failed has `"error": "..."` instead of `"result"` (for example a file that does not exist). The exit code is 1 if any query failed and 2 if the input is invalid. ty's own log is discarded; use `--ty-stderr FILE` to keep it when debugging.
