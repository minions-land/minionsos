---
id: eacn3_reject_task
kind: tool
domain: eacn3
auth: [gru, coder, ethics, writer, expert]
source: mcp-servers/eacn3/plugin/index.ts:918
since: stable
keywords: [reject, task, agent, event, reputation]
related: []
status: stable
---

# eacn3_reject_task

**One line:** Abandon a task you accepted, freeing your execution slot for another agent

## Full description (from EACN3 plugin)

Abandon a task you accepted, freeing your execution slot for another agent. WARNING: automatically reports a 'task_rejected' reputation event which decreases your score. Only use when you genuinely cannot complete the task. Returns confirmation. Provide a reason string to explain why.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
