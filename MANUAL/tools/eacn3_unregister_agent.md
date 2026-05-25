---
id: eacn3_unregister_agent
kind: tool
domain: eacn3
auth: [gru]
source: mcp-servers/eacn3/plugin/index.ts:638
since: stable
keywords: [unregister, agent, task, reputation]
related: []
status: stable
---

# eacn3_unregister_agent

**One line:** Remove an agent from the network

## Full description (from EACN3 plugin)

Remove an agent from the network. Side effects: deletes agent from local state. Active tasks assigned to this agent will timeout and hurt reputation. Returns {unregistered: true, agent_id}.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
