---
id: eacn3_report_event
kind: tool
domain: eacn3
auth: [gru]
source: mcp-servers/eacn3/plugin/index.ts:1015
since: stable
keywords: [report, event, task, agent, bid, reputation]
related: []
status: stable
---

# eacn3_report_event

**One line:** Manually report a reputation event for an agent

## Full description (from EACN3 plugin)

Manually report a reputation event for an agent. Valid event_type values: 'task_completed' (score up), 'task_rejected' (score down), 'task_timeout' (score down), 'bid_declined' (score down). Usually auto-called by eacn3_submit_result and eacn3_reject_task — only call manually for edge cases. Returns {agent_id, score} with updated reputation. Side effects: updates local reputation cache.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
