# minionsos MCP — doc card

The `minionsos` MCP server is the largest and most-used MCP in this repo, but its physical code lives at `minions/tools/mcp/`, not under this directory. This card explains why and points to the actual entry.

## Where it lives

```
minions/tools/mcp_server.py        # 50-line shim — preserves `python -m minions.tools.mcp_server`
minions/tools/mcp/                 # package; each submodule registers its @mcp.tool() decorators on import
├── __init__.py                    # owns the FastMCP singleton; imports every submodule for side effects
├── _common.py                     # _MINIONS_MCP_TOOL_NAMES, _require_tool_allowed, shared arg models
├── experiment_tools.py            # mos_exp_* / exp_queue_* / exp_gpu_pool_*
├── memory_tools.py                # mos_draft_*, mos_shelf_*, mos_book_*
├── paper_tools.py                 # search_arxiv / search_pubmed / read_*_paper / download_*
├── project_tools.py               # mos_project_create / close / dormant / revive / kill / list / set_phase
├── publish_tools.py               # mos_publish_to_shared
├── reel_tools.py                  # mos_reel_get / mos_reel_window
├── runtime_tools.py               # mos_await_events, mos_reset_context, mos_compact_context, mos_review_run
├── signboard_tools.py             # mos_signboard_*
├── spawn_tools.py                 # mos_spawn_role / spawn_expert / dismiss_role / list_roles / kill_role / attach_role
└── visual_tools.py                # mos_visual_render / inspect / check
minions/tools/                     # sibling implementation modules the MCP submodules import
├── publish.py                     # backs publish_tools.py
├── experiment_ssh.py              # backs experiment_tools.py
├── experiment_scheduler.py        # SQLite experiment queue
├── paper_search.py                # backs paper_tools.py
├── await_events.py                # mos_await_events handler
├── draft.py                  # backs memory_tools.py (draft portion)
├── book.py                        # backs memory_tools.py (book portion)
├── shelf.py                       # backs memory_tools.py (shelf portion)
├── reel.py                        # backs reel_tools.py — L0 raw session traces
├── project_bridge.py              # mos_project_bridge
├── reset.py                       # mos_reset_context
├── review.py                      # mos_review_run
├── visual_check.py                # backs visual_tools.py — Poppler render + OpenCV detectors
└── whitelist.py                   # tool surface gating helper
```

The package was split out of the original 1700-line `mcp_server.py` in v11.1 (commit b5d5fe6). `minions/tools/mcp_server.py` is a thin re-export shim kept for the entry-point path and for legacy `from minions.tools.mcp_server import …` imports in tests.

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

Both invocations resolve through Python's module path, not a filesystem path — that's why moving the package would require coordinated changes across CLAUDE.md, AGENTS.md, the test suite, and the many `from minions.tools.publish import ...` style imports inside the package.

## Why it does NOT live in `mcp-servers/`

The other two MCPs in this repo (`eacn3`, `codex-subagent`) are independent Node processes. `.mcp.json` launches them with `node <path>/server.js`, so their physical filesystem path *is* the entry point.

`minionsos` is different: it is a thin FastMCP shell over the rest of the Python package. The submodules under `minions/tools/mcp/` import siblings from `minions/tools/`, plus `minions/lifecycle/`, `minions/state/`, `minions/config`, etc. Pulling the package out into `mcp-servers/minionsos/` would mean either:

1. Cross-package imports from `mcp-servers/` back into `minions/`, which inverts the dependency direction (`mcp-servers/` is supposed to be the outer shell, `minions/` the core).
2. A Python package named `mcp-servers` (illegal — hyphen) or `mcp_servers` (a new top-level package just to host one file).
3. Touching `tests/unit/test_mcp_authz.py:10` (`from minions.tools.mcp_server import _require_tool_allowed`) and any other internal users.

None of these increase clarity; they trade a clean import graph for a tidier `ls`. The decision is to keep `minionsos` MCP coupled to its package and document it here so the registry remains discoverable from a single place.

## Tools exposed (selection)

See `minions/tools/mcp/_common.py:_MINIONS_MCP_TOOL_NAMES` for the authoritative list. Categories:

- **Project lifecycle**: `mos_project_create`, `mos_project_close`, `mos_project_kill`, `mos_project_dormant`, `mos_project_revive`, `mos_project_list`, `mos_project_set_phase`, `mos_project_checkpoint_workspace`, `mos_project_bridge`.
- **Role lifecycle**: `mos_spawn_role`, `mos_spawn_expert`, `mos_dismiss_role`, `mos_list_roles`, `mos_kill_role`, `mos_attach_role`.
- **Cross-role IO**: `mos_publish_to_shared`, `mos_draft_*`, `mos_book_ingest`, `mos_book_ingest_batch`, `mos_book_query`, `mos_book_save_synthesis`, `mos_book_lint`, `mos_book_audit_walk`, `mos_book_resolve_contradiction`, `mos_book_promote_verified`, `mos_book_crystallize_session`.
- **Event loop**: `mos_await_events`, `mos_noter_wait`, `mos_get_events`, `mos_unread_summary`, `mos_reset_context`, `mos_compact_context`.
- **Review**: `mos_review_run`.
- **Experiments**: `mos_exp_run`, `mos_exp_status`, `mos_exp_wait`, `mos_exp_kill`, `mos_exp_list`, `mos_exp_put`, `mos_exp_get`, `mos_exp_tail`, `mos_query_gpus`, `mos_exp_queue_*`, `mos_exp_gpu_pool_*`.
- **Paper search**: `mos_search_arxiv`, `mos_search_pubmed`, `mos_search_biorxiv`, `mos_search_medrxiv`, `mos_search_google_scholar`, `mos_search_semantic`, `mos_search_papers_federated`, `mos_resolve_arxiv_ids`, `mos_read_*_paper`, `mos_download_*`.
- **Visual format-check**: `mos_visual_render`, `mos_visual_inspect`, `mos_visual_check` — Poppler rasterize + pixel-level defect detection (column void, edge overflow, trailing whitespace, column imbalance, float clustering, short lines). Available to all EACN-visible roles; denied to Noter.
- **Reel (L0) drill-down**: `mos_reel_get`, `mos_reel_window` — read raw session traces archived under `branches/<role>/reel/<session_id>/` by the `reel_capture` PostToolUse hook. Available to all EACN-visible roles for their own reel; Gru can read cross-role reels. Noter is excluded — it does not consume reel-level data.
- **Signboard**: `mos_signboard_read`, `mos_signboard_set`, `mos_signboard_evaluate`, `mos_signboard_consume`, `mos_signboard_reopen`.
- **Diagnostics**: `mos_issue_report`, `mos_start_monitor`, `mos_list_workflow_plugins`.

Access control is two-layered: `minions/config/__init__.py:resolve_whitelist` produces the `--allowed-tools` CLI surface (model-visible), and `minions/config/__init__.py:resolve_server_authz` produces the server-side enforcement set checked by `_require_tool_allowed` in `minions/tools/mcp/_common.py` before each call.

## Adding a new tool

1. Implement the underlying logic under `minions/tools/<area>.py` (or in a new module).
2. Add the FastMCP wrapper to the appropriate domain submodule under `minions/tools/mcp/<area>_tools.py` — `@mcp.tool()` decorator, Pydantic argument class, and a `_require_tool_allowed("<name>")` line at the top of the body. Create a new submodule if no existing one fits, then add it to the import tuple in `minions/tools/mcp/__init__.py`.
3. Add the tool name to `_MINIONS_MCP_TOOL_NAMES` in `minions/tools/mcp/_common.py`.
4. Update `minions/config/__init__.py` — both `_EACN_ROLE_MAIN_TOOLS` (CLI surface, all EACN roles unified for KV-cache parity) and the per-role entries in `_SERVER_AUTHZ` (real enforcement boundary). Most tools are gated by role; if it should be available everywhere, follow the `_KEEPALIVE_TOOLS` / `_ISSUE_REPORT_TOOLS` pattern.
5. Add an authz regression case to `tests/unit/test_mcp_authz.py` covering one allowed role and one denied role.
6. Add functional unit coverage for the underlying tool logic under `tests/unit/`.
7. Update the tool/write boundary table in root `CLAUDE.md` if the tool changes any role's effective surface.

The other two MCPs don't share this workflow — they have their own internal organisation under `mcp-servers/eacn3/` and `mcp-servers/codex-subagent/`.
