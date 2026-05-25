---
id: eacn3_claim_agent
kind: tool
domain: eacn3
auth: [gru]
source: mcp-servers/eacn3/plugin/index.ts:502
since: stable
keywords: [claim, agent, event]
related: []
status: stable
---

# eacn3_claim_agent

**One line:** Claim a previously registered agent from disk into this session

## Full description (from EACN3 plugin)

Claim a previously registered agent from disk into this session. Use this to resume an agent listed in available_agents from eacn3_connect. The agent is re-registered on the network and event transport is started. Only one agent per session.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
