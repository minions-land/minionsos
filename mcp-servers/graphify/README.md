# mcp-servers/graphify

Per-project graphify (project-local Shelf graph — L3 structural index) for MinionsOS.

## Purpose

Bottom-up structural index over a project's `branches/shared/{book,notes,ethics,exp}/`
artifacts. Complements the Draft (L1 — process memory) and the
Book (L2 — compiled product memory) by giving every Role a queryable
graph of cross-document relationships, god-nodes, and communities.

The third-party CLI is still called `graphify`; the MinionsOS-side
concept it produces is the project's **Shelf graph**, written to
`branches/shared/shelf/shelf.json`.

See dev-log entry `dev-log/2026-05.md` → "Book pattern (L2) + Shelf (L3) phased plan".

## Lifecycle

- **Build**: Noter's periodic wake (`mos_noter_wait`) calls `extract.py`
  if any source file under `branches/shared/{book,notes,ethics,exp}/`
  is newer than the existing `shelf.json`. Extract is gated behind a
  5-minute subprocess timeout.
- **Serve**: `.mcp.json` registers `graphify` as a stdio MCP server
  pointing at `launcher.sh`. The launcher resolves
  `project_${MINIONS_PROJECT_PORT}/branches/shared/shelf/shelf.json`
  and execs `python -m graphify.serve` from the local `.venv`.

## Setup (one-time)

```bash
cd mcp-servers/graphify
VIRTUAL_ENV="$PWD/.venv" uv venv
VIRTUAL_ENV="$PWD/.venv" uv pip install -e .
.venv/bin/graphify --help | head -3   # confirm 0.8.x
```

This is intentionally isolated from the main project venv so graphify's
heavy tree-sitter dependency tree does not pollute MinionsOS deps.

## MCP tools exposed

Read-only, whitelisted for every main role:
`query_graph`, `get_node`, `get_neighbors`, `get_community`,
`god_nodes`, `graph_stats`, `shortest_path`.

Roles see them as `mcp__graphify__<name>`. The whitelist is in
`minions/config/__init__.py:_GRAPHIFY_READ_TOOLS`.

## Cost

- Extract uses `--backend claude-cli` → routes through the host Claude
  Code session. $0 in API spend; counts against the same context budget
  as the Role that triggered it. Noter only triggers when shared/
  artifacts have actually changed.
- Serve is cheap stdio I/O.

## Non-goals

- No write-back to `shelf.json` from MCP — only Noter rebuilds.
- No cross-project graph at this layer (the global L3 Shelf at
  `~/.minionsos/shelf.json` is built by `mos_shelf_register` aggregating
  per-project graphs).
- No `graphify prs` integration (deferred to Phase 8 / review-scope decider).
