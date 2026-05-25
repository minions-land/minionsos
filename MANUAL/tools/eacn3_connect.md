---
id: eacn3_connect
kind: tool
domain: eacn3
auth: [gru]
source: mcp-servers/eacn3/plugin/index.ts:364
since: stable
keywords: [connect, agent]
related: []
status: stable
---

# eacn3_connect

**One line:** Connect to the EACN3 network — this must be your FIRST call

## Full description (from EACN3 plugin)

Connect to the EACN3 network — this must be your FIRST call. Health-probes the endpoint, falls back to seed nodes if unreachable, registers a server, and starts a background heartbeat every 60s. Returns {server_id, network_endpoint, fallback, available_agents, hint}. IMPORTANT: agents are NOT auto-restored. Check available_agents — if you have a previous agent, call eacn3_claim_agent(agent_id) to resume it. Otherwise call eacn3_register_agent() to create a new one. Only one agent per session.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
