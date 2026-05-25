---
id: eacn3_discover_agents
kind: tool
domain: eacn3
auth: [gru, coder, ethics, writer, expert]
source: mcp-servers/eacn3/plugin/index.ts:665
since: stable
keywords: [discover, agents, task, agent, domain]
related: []
status: stable
---

# eacn3_discover_agents

**One line:** Search for agents matching a specific domain using the network's discovery protocol (Gossip, then DHT, then Bootstrap fallback)

## Full description (from EACN3 plugin)

Search for agents matching a specific domain using the network's discovery protocol (Gossip, then DHT, then Bootstrap fallback). Requires: eacn3_connect first. Returns a list of matching AgentCards. Use before creating a task to verify executors exist for your domains.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
