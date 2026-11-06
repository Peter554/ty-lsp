---
name: ty-lsp
description: Answers code navigation questions about Python code with ty - where a name is defined, what references it, who calls a function, what a function calls, and a class's subtypes and supertypes. Use instead of grep when you need exact, type-aware results.
---

# ty-lsp

`ty-lsp` queries Python code with ty's language server. Prefer it over grep for questions about definitions, usages, call graphs and class hierarchies: results follow imports, re-exports and inferred types.

**Always use `-f text` (`--format text`) for compact, agent-readable output.** Run it from the project root (or pass `--root DIR`). A position is `PATH:LINE:COLUMN` with **1-based** line and column, pointing at a name (a definition or any usage).

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
ty-lsp subtypes PATH:LINE:COLUMN          # Classes in the project inheriting from a class
ty-lsp supertypes PATH:LINE:COLUMN        # Base classes of a class
```

`callers`, `callees`, `subtypes` and `supertypes` take `--all` (indirect too) and `--max-depth N` (implies `--all`). `callees` also takes `--within DIR` (implies `--all`).

## Tips

- Instead of `PATH:LINE:COLUMN`, any position command accepts `PATH:NAME` for a symbol defined in the file, e.g. `ty-lsp callers src/a.py:Class.method`. If the name is not found or is defined more than once, that query fails with the candidate positions - repeat it with one of them.
- To find positions, use `symbols PATH` or `symbol PATH:NAME`, which give the location of names.
- Pass several queries in one run - the server starts once: `ty-lsp references a.py:3:5 b.py:8:1`. Or use `--stdin` / `--file FILE` with one query per line.
- Prefer `callers`/`callees` without `--all` first; the indirect graph (especially callees, which include the standard library) can be large. Limit it with `--max-depth` or `--within`.
- Read results with care for empty ones: an empty result means ty found nothing, such as a dynamic call it cannot resolve.

## Output

With `-f text`, each query has a `## query` heading followed by one line per result, with paths relative to the current directory:

```
## src/a.py:3:5
src/b.py:9:5                                   # definition, references, ...
mid_a src/g.py:7:5 calls src/g.py:4:5 at src/g.py:8:5   # callers: NAME LOCATION calls CALLEE at CALL_SITES
src/g.py:15:5 calls mid_a src/g.py:7:5 at src/g.py:16:5   # callees: CALLER calls NAME LOCATION at CALL_SITES
Square src/s.py:7:7 subtype of src/s.py:4:7   # subtypes (and "supertype of" for supertypes)
```

A failed query prints `error: ...` and an empty one prints `(none)`. The exit code is 1 if any query failed and 2 if the input is invalid. ty's own log is discarded; use `--ty-stderr FILE` to keep it when debugging.

Without `-f text` the output is JSON: a list with one entry per query, each `{"query": {"raw", "parsed"}, "result": [...]}` or `{"query": ..., "error": "..."}`.
