---
id: eacn3_reverse_control_status
kind: tool
domain: eacn3
auth: [gru]
source: mcp-servers/eacn3/plugin/index.ts:1128
since: stable
keywords: [reverse, control, status, agent, event]
related: []
status: stable
---

# eacn3_reverse_control_status

**One line:** Get the current status of the MCP reverse control engine

## Full description (from EACN3 plugin)

Get the current status of the MCP reverse control engine. Shows whether sampling is available (always false in OpenClaw — use eacn3_await_events instead), configured agents, pending directive count, and rate limiting info.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
