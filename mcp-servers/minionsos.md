# minionsos MCP — doc card

The `minionsos` MCP server is the largest and most-used MCP in this repo, but its physical code lives at `minions/tools/mcp_server.py`, not under this directory. This card explains why and points to the actual entry.

## Where it lives

```
minions/tools/mcp_server.py        # 1207 lines — the FastMCP entry
minions/tools/                     # 14 sibling modules the server imports from
├── publish.py                     # mos_publish_to_shared
├── experiment_ssh.py              # mos_exp_*, exp_queue_*, exp_gpu_pool_*
├── experiment_scheduler.py        # SQLite experiment queue
├── paper_search.py                # search_arxiv / search_pubmed / etc.
├── await_events.py                # mos_await_events
├── exploration_dag.py             # mos_dag_*
├── project_bridge.py              # mos_project_bridge
├── reset.py                       # mos_reset_context
├── review.py                      # mos_review_run
├── events_log.py
├── get_events.py
├── utils.py
└── whitelist.py                   # tool surface gating
```

## How it is registered

`.mcp.json` (Claude Code):
```json
"minionsos": {
  "type": "stdio",
  "command": "uv",
  "args": ["run", "--project", ".", "python", "-m", "minions.tools.mcp_server"]
}
```

`.codex/config.toml` (Codex):
```toml
[mcp_servers.minionsos]
command = "uv"
args = ["run", "--project", ".", "python", "-m", "minions.tools.mcp_server"]
```

Both invocations resolve through Python's module path, not a filesystem path — that's why moving the file would require coordinated changes across CLAUDE.md, AGENTS.md, the test suite, and 50+ `from minions.tools.publish import ...` style imports inside the package.

## Why it does NOT live in `mcp-servers/`

The other two MCPs in this repo (`eacn3`, `codex-subagent`) are independent Node processes. `.mcp.json` launches them with `node <path>/server.js`, so their physical filesystem path *is* the entry point.

`minionsos` is different: it is a thin FastMCP shell over the rest of the Python package. It imports 14 sibling modules under `minions/tools/`, plus `minions/lifecycle/`, `minions/state/`, `minions/config`, etc. Pulling `mcp_server.py` out into `mcp-servers/minionsos/` would mean either:

1. Cross-package imports from `mcp-servers/` back into `minions/`, which inverts the dependency direction (`mcp-servers/` is supposed to be the outer shell, `minions/` the core).
2. A Python package named `mcp-servers` (illegal — hyphen) or `mcp_servers` (a new top-level package just to host one file).
3. Touching `tests/unit/test_mcp_authz.py:10` (`from minions.tools.mcp_server import _require_tool_allowed`) and any other internal users.

None of these increase clarity; they trade a clean import graph for a tidier `ls`. The decision is to keep `minionsos` MCP coupled to its package and document it here so the registry remains discoverable from a single place.

## Tools exposed (selection)

See `minions/tools/mcp_server.py:_MINIONS_MCP_TOOL_NAMES` for the authoritative list. Categories:

- **Project lifecycle**: `mos_project_create`, `mos_project_close`, `mos_project_kill`, `mos_project_dormant`, `mos_project_revive`, `mos_project_list`, `mos_project_set_phase`, `mos_project_checkpoint_workspace`, `mos_project_bridge`.
- **Role lifecycle**: `mos_spawn_role`, `mos_spawn_expert`, `mos_dismiss_role`, `mos_list_roles`.
- **Cross-role IO**: `mos_publish_to_shared`, `mos_dag_append`, `mos_dag_query`, `mos_dag_summary`, `mos_dag_annotate`, `mos_dag_path`, `mos_dag_commit_shared`.
- **Event loop**: `mos_await_events`, `mos_reset_context`.
- **Review**: `mos_review_run`.
- **Experiments**: `mos_exp_run`, `exp_queue_*`, `exp_gpu_pool_*`.
- **Paper search**: `search_arxiv`, `search_pubmed`, `search_biorxiv`, `search_medrxiv`, `search_google_scholar`, `read_arxiv_paper`, `read_pubmed_paper`, `download_*`.

Access control is in `minions/tools/whitelist.py:resolve_whitelist`. The MCP server enforces it via `_require_tool_allowed` before each call.

## Adding a new tool

1. Implement it under `minions/tools/<area>.py`.
2. Register it in `mcp_server.py` (FastMCP `@mcp.tool` decorator + appropriate `BaseModel` argument class).
3. Add it to `_MINIONS_MCP_TOOL_NAMES`.
4. Update `minions/tools/whitelist.py` if it should be available to specific roles only.
5. Add unit coverage under `tests/unit/`.

The other two MCPs don't share this workflow — they have their own internal organisation under `mcp-servers/eacn3/` and `mcp-servers/codex-subagent/`.
