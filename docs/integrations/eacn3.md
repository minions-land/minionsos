# EACN3 — Per-Project Coordination Backend

## What we use

| Surface | Purpose | Where |
|---|---|---|
| HTTP API (`/api/agents`, `/api/tasks`, `/api/events/{id}`, `/api/messages`) | Role registration, task lifecycle, event delivery | `minions/lifecycle/eacn_client.py` |
| Node MCP plugin (`mcp-servers/eacn3/plugin/`) | Exposes `eacn3_*` tools to Claude Code roles | `.mcp.json` → `mcp-servers/eacn3/plugin/dist/server.js` |
| SQLite backend (`project_{port}/eacn3_data/eacn3.db`) | Per-project persistent state | Started by `minions/lifecycle/project.py` |

## Version lock

EACN3 is a **local editable dependency** — its source lives at `mcp-servers/eacn3/`
and is referenced in the root `pyproject.toml`:
```toml
[tool.uv.sources]
eacn3 = { path = "mcp-servers/eacn3", editable = true }
```

There is no PyPI version. We own the source. The Node plugin is built from
`mcp-servers/eacn3/plugin/` via `npm run build`.

## What we explicitly avoid

- **`team_setup` and cluster federation** — fully built but unused (see memory
  `project_eacn3_untapped_capabilities`). We use single-project backends only.
- **`gru_relay`** — a workaround for native peer routes that we haven't needed
  since the project-bridge tool was added.
- **Direct HTTP calls from role code** — roles use `eacn3_*` MCP tools, never
  raw HTTP. The only direct HTTP caller is `minions/lifecycle/eacn_client.py`
  (used by lifecycle code, not by roles).

## Brittle points

1. **Event delivery contract.** `GET /api/events/{agent_id}` is a long-poll
   that drains on read. If the API changes to not-drain or adds pagination,
   `mos_await_events` breaks. Mitigation: we own the source.
2. **SQLite schema.** If we add columns to the EACN3 schema, existing
   `eacn3.db` files from running projects need migration. Mitigation:
   EACN3 has `alembic`-style auto-migration on startup.
3. **Node plugin tool names.** The MCP plugin exposes `eacn3_send_message`,
   `eacn3_create_task`, etc. If renamed, every role's whitelist + SYSTEM.md
   breaks. Mitigation: we own the plugin; changes are deliberate.

## Adaptation rule (from memory)

> Roles adapt to existing EACN3 primitives; never grow EACN3 to fit a Role gap.

If a Role needs behavior EACN3 doesn't offer, build an adapter in
`minions/lifecycle/` or `minions/tools/`, not a new EACN3 endpoint.

## Upgrade path

Since we own the source, "upgrade" means "edit mcp-servers/eacn3/ and rebuild":
1. Edit Python source under `mcp-servers/eacn3/`.
2. `uv sync` (editable dep auto-refreshes).
3. Edit Node plugin under `mcp-servers/eacn3/plugin/`, then `cd plugin && npm run build`.
4. Run `uv run pytest tests/unit/ -x -q` — full suite must pass.
5. Test with a live project: `./mos project create`, verify backend starts.

## Fallback when unavailable

If the EACN3 backend fails to start, `mos_project_create` raises and the
project cannot be created. There is no degraded mode — EACN3 is the
coordination backbone.
