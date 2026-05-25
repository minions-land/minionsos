---
id: eacn3_a2a_server
kind: tool
domain: eacn3
auth: [gru]
source: mcp-servers/eacn3/plugin/index.ts:464
since: stable
keywords: [a2a, server, agent, message]
related: []
status: stable
---

# eacn3_a2a_server

**One line:** Start or stop the A2A (Agent-to-Agent) HTTP server for direct messaging

## Full description (from EACN3 plugin)

Start or stop the A2A (Agent-to-Agent) HTTP server for direct messaging. When started, other agents can POST messages directly to this server instead of relaying through the network. Returns {running, port, url}. Pass action='stop' to shut it down. After starting, re-register agents or call eacn3_update_agent to advertise the real URL.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
