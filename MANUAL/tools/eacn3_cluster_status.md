---
id: eacn3_cluster_status
kind: tool
domain: eacn3
auth: [gru]
source: mcp-servers/eacn3/plugin/index.ts:339
since: stable
keywords: [cluster, status]
related: []
status: stable
---

# eacn3_cluster_status

**One line:** Retrieve the full cluster topology including all member nodes, their online/offline status, and seed URLs

## Full description (from EACN3 plugin)

Retrieve the full cluster topology including all member nodes, their online/offline status, and seed URLs. No prerequisites — works before eacn3_connect. Returns array of node objects with status and endpoint fields. Useful for diagnostics and finding alternative endpoints if primary is down.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
