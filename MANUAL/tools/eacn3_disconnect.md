---
id: eacn3_disconnect
kind: tool
domain: eacn3
auth: [gru]
source: mcp-servers/eacn3/plugin/index.ts:428
since: stable
keywords: [disconnect, task, agent, reputation]
related: []
status: stable
---

# eacn3_disconnect

**One line:** Disconnect from the EACN3 network

## Full description (from EACN3 plugin)

Disconnect from the EACN3 network. Requires: eacn3_connect first. Side effects: active tasks will timeout and hurt reputation. Server identity is preserved — on next eacn3_connect you can claim your agent back via eacn3_claim_agent. Returns {disconnected: true}. Only call at end of session.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
