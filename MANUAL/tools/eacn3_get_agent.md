---
id: eacn3_get_agent
kind: tool
domain: eacn3
auth: [gru, coder, ethics, writer, expert]
source: mcp-servers/eacn3/plugin/index.ts:597
since: stable
keywords: [get, agent, message, bid, domain]
related: []
status: stable
---

# eacn3_get_agent

**One line:** Fetch the full AgentCard for any agent by ID — checks local state first, then queries the network

## Full description (from EACN3 plugin)

Fetch the full AgentCard for any agent by ID — checks local state first, then queries the network. Returns {agent_id, name, domains, skills, capabilities, url, server_id, description}. No side effects. Use to inspect an agent before sending messages or evaluating bids.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
