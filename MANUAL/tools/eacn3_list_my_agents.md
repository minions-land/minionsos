---
id: eacn3_list_my_agents
kind: tool
domain: eacn3
auth: [gru, coder, ethics, writer, expert]
source: mcp-servers/eacn3/plugin/index.ts:654
since: stable
keywords: [list, my, agents, agent, domain]
related: []
status: stable
---

# eacn3_list_my_agents

**One line:** List all agents registered on this local server instance

## Full description (from EACN3 plugin)

List all agents registered on this local server instance. Returns {count, agents[]} where each agent includes agent_id, name, domains, tier, and registered status. No network call — reads local state only. Use to check which agents are active.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
