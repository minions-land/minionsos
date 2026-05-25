---
id: eacn3_register_agent
kind: tool
domain: eacn3
auth: [gru]
source: mcp-servers/eacn3/plugin/index.ts:531
since: stable
keywords: [register, agent, task, event, domain, subtask, broadcast]
related: []
status: stable
---

# eacn3_register_agent

**One line:** Create and register an agent identity on the EACN3 network

## Full description (from EACN3 plugin)

Create and register an agent identity on the EACN3 network. Requires: eacn3_connect first. Assembles an AgentCard, registers it with the network, persists it locally, and registers it for on-demand event fetching (task_broadcast, subtask_completed, etc.). Returns {agent_id, seeds, domains}. Domains control which task broadcasts you receive — be specific (e.g. 'python-coding' not 'coding').

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
