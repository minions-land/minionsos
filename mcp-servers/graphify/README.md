# mcp-servers/graphify

Per-role graphify (optional structural graph — formerly L3 Shelf) for MinionsOS.

## Purpose

Structural index over a role's private workspace artifacts. Each Role that
wants graph-assisted retrieval runs its own graphify instance pointing at its
own `branches/{role}/graphify-out/graph.json`. This replaces the previous
project-level shared Shelf (`branches/shared/shelf/shelf.json`), which was
removed in the Memory V2 refactor (2026-05).

The third-party CLI is still called `graphify`; MinionsOS wires it as a
per-role optional MCP server.

## Lifecycle

- **Build**: Roles build their own graph on demand (e.g. via `graphify extract`)
  in their own branch workspace. No shared cron; no Noter involvement.
- **Serve**: `.mcp.json` registers `graphify` as a stdio MCP server pointing
  at `launcher.sh`. The launcher requires both `MINIONS_PROJECT_PORT` and
  `MINIONS_ROLE_NAME` env vars and resolves:
  `project_${PORT}/branches/${ROLE}/graphify-out/graph.json`.

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

Read-only, whitelisted for all main roles **except** Noter:
`query_graph`, `get_node`, `get_neighbors`, `get_community`,
`god_nodes`, `graph_stats`, `shortest_path`.

Roles see them as `mcp__graphify__<name>`. The whitelist is in
`minions/config/__init__.py`.

## Non-goals

- No shared/global Shelf — each role's graph is private to that role.
- No automatic extract on Noter wake — `extract.py` has been deleted.
- No cross-project graph at this layer.
