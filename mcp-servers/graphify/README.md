# mcp-servers/graphify

Per-project graphify (Layer 3 structural index) for MinionsOS.

## Purpose

Bottom-up structural index over a project's `branches/shared/{wiki,notes,ethics,exp}/`
artifacts. Complements the DAG (Layer 0 — process memory) and the Wiki
(Layer 2 — compiled product memory) by giving every Role a queryable
graph of cross-document relationships, god-nodes, and communities.

See dev-log entry `dev-log/2026-05.md` → "Wiki-as-Layer-2 design + phased plan".

## Lifecycle

- **Build**: Noter's periodic wake (`mos_noter_wait`) calls `extract.py`
  if any source file under `branches/shared/{wiki,notes,ethics,exp}/`
  is newer than the existing `corpus_graph.json`. Extract is gated
  behind a 5-minute subprocess timeout.
- **Serve**: `.mcp.json` registers `graphify` as a stdio MCP server
  pointing at `launcher.sh`. The launcher resolves
  `project_${MINIONS_PROJECT_PORT}/branches/shared/exploration/corpus_graph.json`
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

- No write-back to `corpus_graph.json` from MCP — only Noter rebuilds.
- No cross-project graph (deferred to Phase 9 / global graph).
- No `graphify prs` integration (deferred to Phase 8 / review-scope decider).
