# mcp-servers/codegraph

Per-project code knowledge graph (Coder's L3 structural index over source) for MinionsOS.

## Purpose

Bottom-up structural index over a project's **code**, complementing
`mcp-servers/graphify/` which indexes a project's **prose** (book / notes /
ethics / experiment artifacts under `branches/shared/`). Together they form
MinionsOS's two L3 surfaces: graphify is the Shelf graph over written
artifacts, codegraph is the Coder graph over source files.

The third-party CLI is `@colbymchenry/codegraph` (TypeScript, MIT, npm
package on the upstream registry). It uses tree-sitter to extract
symbol-level nodes (functions, classes, methods) and edges
(calls, imports, extends, implements, framework routes) into a local
SQLite database with FTS5 full-text search. No LLM is ever called —
extraction is fully deterministic, $0 in API spend, ~1 second of
file-watcher debounce after every save.

The MinionsOS-side concept it produces is the project's **Coder graph**,
written to `branches/coder/.codegraph/codegraph.db`. A second
repository-level graph at `<repo>/.codegraph/codegraph.db` covers
MinionsOS's own runtime code so Coder can do system-maintenance impact
analysis without conflating the two scopes.

See dev-log entry `dev-log/2026-05.md` for the rollout decision and the
two-graph integration design.

## Why this is not just "another graphify"

| | graphify (Shelf) | codegraph (Coder graph) |
|---|---|---|
| Input | Markdown / PDFs / notes under `branches/shared/` | Source code under `branches/coder/` and `<repo>/` |
| Extraction | LLM-backed (`graphify extract --backend claude-cli`) | tree-sitter AST, no LLM |
| Cost per rebuild | Counts against host Claude Code context | $0, deterministic |
| Trigger | Noter periodic wake (rebuilds when sources change) | Built-in OS file watcher (FSEvents/inotify), ~1s debounce, self-syncing |
| Granularity | Concept / entity nodes, community detection | Symbol-level nodes, call / import / route edges |
| Best query | "What god-nodes connect these two papers?" | "What calls `train_model`? What breaks if I rename it?" |

The lifecycle gap is the load-bearing difference: graphify *must* batch
because every rebuild costs LLM tokens, so Noter cron is the right
shape. Codegraph *cannot* benefit from batching — its index is cheap
and stale data costs Coder more than fresh extraction costs the system.
The launcher therefore starts the watcher on first MCP connect; no
periodic wake involved.

## Lifecycle

- **Bootstrap (one-time per scope)**: The SQLite index must exist
  before the launcher will start. `install.sh` warms the repo scope by
  running `codegraph init -i` once at install time. Project scope is
  materialized by `ensure_role_workspace(port, "coder")` in
  `minions/lifecycle/project.py`, which runs `codegraph init -i` in
  `branches/coder/` when the Coder worktree is first created. Both
  bootstraps are idempotent (skip if `.codegraph/` exists) and
  non-fatal (failure warns; the launcher's error message tells the
  operator how to recover manually).
- **Why bootstrap is out-of-band**: `codegraph init -i` does an
  initial tree-sitter pass that on a large repository takes tens of
  seconds. Running it inside the MCP handshake would time out the
  connection and leave Roles without the surface. The launcher
  fail-fasts on a missing index with a clear bootstrap instruction
  rather than retrying silently.
- **Incremental updates**: Once the index exists, `codegraph serve
  --mcp` starts a bundled OS-event watcher (FSEvents/inotify) with
  ~2s debounce. Every Coder save triggers a sub-second incremental
  re-index. No agent action needed; no LLM tokens consumed.
- **Serve**: `.mcp.json` registers `codegraph` as a stdio MCP server
  pointing at `launcher.sh`. The launcher resolves the right
  `.codegraph/codegraph.db` from `MINIONS_PROJECT_PORT` (project
  scope) or falls back to repository scope, then execs `codegraph
  serve --mcp` from this directory's local `node_modules`.

## Setup (one-time)

```bash
cd mcp-servers/codegraph
npm install                              # installs @colbymchenry/codegraph + deps
node_modules/.bin/codegraph --version    # confirm 0.9.x
```

This is intentionally isolated from the EACN3 plugin's `node_modules`
so the tree-sitter wasm grammars do not pollute MinionsOS's other Node
servers. The bundle ships with its own Node runtime — host Node
version drift cannot break extraction.

## MCP tools exposed

Read-only, whitelisted per role (see `minions/config/__init__.py:_CODEGRAPH_READ_TOOLS`):

| Tool | Coder | Expert | Ethics | Writer / Noter / Gru |
|---|---|---|---|---|
| `mcp__codegraph__codegraph_search` | yes | yes | yes | no |
| `mcp__codegraph__codegraph_callers` | yes | yes | yes | no |
| `mcp__codegraph__codegraph_callees` | yes | yes | yes | no |
| `mcp__codegraph__codegraph_impact` | yes | yes | yes | no |
| `mcp__codegraph__codegraph_node` | yes | yes | yes | no |
| `mcp__codegraph__codegraph_files` | yes | yes | yes | no |
| `mcp__codegraph__codegraph_status` | yes | yes | yes | no |
| `mcp__codegraph__codegraph_context` | yes | yes | no | no |
| `mcp__codegraph__codegraph_explore` | yes | yes | no | no |

`codegraph_context` and `codegraph_explore` are gated to Coder + Expert
because they return large source-code sections and can blow up
context budget for roles that only need provenance trails (Ethics) or
prose work (Writer). The lighter symbol / caller / impact tools are
safe to expose universally.

## Cost

- **Extraction**: $0 in API spend. tree-sitter AST is deterministic.
  CPU-bound but fast (VS Code's 10k files index in roughly a minute on
  first run; incremental updates are sub-second).
- **Serve**: cheap stdio I/O. Sub-millisecond SQLite reads via FTS5
  and the indexed `(source, kind)` / `(target, kind)` composites.
- **Storage**: local SQLite in WAL mode. Concurrent reads never block
  on the watcher's writes.

## Two-graph integration with graphify

graphify and codegraph index disjoint data and update on different
clocks, but a single Coder change can move both surfaces (e.g. an
experiment script lands in `branches/coder/`, then its results write
into `branches/shared/exp/exp-<id>/`). The integration plan:

1. **No shared SQLite, no shared graph.json.** Each tool keeps its
   own store at its native path. Forcing them into one schema would
   break either graphify's community detection or codegraph's
   sub-millisecond AST queries.
2. **Cross-reference via shared node ids.** When graphify ingests an
   experiment report that mentions a code symbol, the resulting node
   carries `source_file: branches/coder/src/.../foo.py`. Coder /
   Expert can pivot from a graphify node into a codegraph
   `codegraph_search` by that symbol name. The pivot is agent-side,
   not protocol-side — no glue server needed.
3. **Update independence.** Codegraph's watcher fires on every Coder
   save; graphify's Noter cron fires when shared/ changes. Neither
   triggers the other. The contract is "if you want both fresh, query
   both" — the agent is responsible for knowing which side a
   question lives on.
4. **`mos_shelf_register` aggregates only graphify graphs**, as today.
   Codegraph stays project-local; cross-project code analysis is out of
   scope (and would be misleading given dependency / language drift
   between projects).

## Non-goals

- **No write-back from MCP**: tools are read-only. The watcher is the
  only writer.
- **No cross-project code graph at `~/.minionsos/`**: codegraph stays
  per-project (and one repository-level scope for system-maintenance
  code). The global L3 Shelf at `~/.minionsos/shelf.json` aggregates
  graphify graphs only.
- **No LLM extraction path**: if we ever need semantic edges over
  code (concept-level, "two functions that do the same thing"),
  that lives in graphify's domain, not here.
- **No replacement for the TypeScript compiler / linter / test
  suite**: codegraph is structural context, not correctness
  validation. Coder still runs the project's own gates after edits.
- **No live cross-language symbol resolution beyond best-effort name
  matching** (codegraph's own README §Limitations). Ambiguous calls
  return multiple candidates rather than guessing.
