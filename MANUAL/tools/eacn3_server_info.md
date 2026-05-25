---
id: eacn3_server_info
kind: tool
domain: eacn3
auth: [gru, coder, ethics, writer, expert]
source: mcp-servers/eacn3/plugin/index.ts:451
since: stable
keywords: [server, info, task, agent]
related: []
status: stable
---

# eacn3_server_info

**One line:** Get current server connection state, including server_card, network_endpoint, registered agent IDs, task count, and remote status

## Full description (from EACN3 plugin)

Get current server connection state, including server_card, network_endpoint, registered agent IDs, task count, and remote status. Requires: eacn3_connect first. Returns {server_card, network_endpoint, agents_count, agents[], tasks_count, remote_status}. No side effects — read-only diagnostic.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
