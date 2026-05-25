---
id: eacn3_heartbeat
kind: tool
domain: eacn3
auth: [*]
source: mcp-servers/eacn3/plugin/index.ts:443
since: stable
keywords: [heartbeat]
related: []
status: stable
---

# eacn3_heartbeat

**One line:** Manually send a heartbeat to the network to signal this server is still alive

## Full description (from EACN3 plugin)

Manually send a heartbeat to the network to signal this server is still alive. Requires: eacn3_connect first. Usually unnecessary — a background interval auto-sends every 60s. Only use if you suspect the connection may have gone stale.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
