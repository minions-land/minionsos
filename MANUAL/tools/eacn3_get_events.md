---
id: eacn3_get_events
kind: tool
domain: eacn3
auth: [gru, coder, ethics, writer, expert]
source: mcp-servers/eacn3/plugin/index.ts:1067
since: stable
keywords: [get, events, task, agent, message, bid, event, subtask, broadcast]
related: []
status: stable
---

# eacn3_get_events

**One line:** Fetch pending events from the network for a specific agent, plus any locally buffered synthetic events

## Full description (from EACN3 plugin)

Fetch pending events from the network for a specific agent, plus any locally buffered synthetic events. Returns {count, events[], reverse_control} where event types include: task_broadcast, bid_request_confirmation, bid_result, discussion_update, subtask_completed, task_collected, task_timeout, adjudication_task, direct_message.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
