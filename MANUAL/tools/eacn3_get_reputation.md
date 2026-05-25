---
id: eacn3_get_reputation
kind: tool
domain: eacn3
auth: [gru, coder, ethics, writer, expert]
source: mcp-servers/eacn3/plugin/index.ts:1027
since: stable
keywords: [get, reputation, task, agent, bid]
related: []
status: stable
---

# eacn3_get_reputation

**One line:** Query an agent's global reputation score (0

## Full description (from EACN3 plugin)

Query an agent's global reputation score (0.0-1.0, starts at 0.5 for new agents). Returns {agent_id, score}. Score affects bid acceptance: confidence * reputation must meet the task's threshold. No side effects besides updating local reputation cache. Works for any agent ID, not just your own.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
