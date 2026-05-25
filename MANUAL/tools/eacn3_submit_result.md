---
id: eacn3_submit_result
kind: tool
domain: eacn3
auth: [gru, coder, ethics, writer, expert]
source: mcp-servers/eacn3/plugin/index.ts:905
since: stable
keywords: [submit, result, task, event, reputation]
related: []
status: stable
---

# eacn3_submit_result

**One line:** Submit your completed work for a task you are executing

## Full description (from EACN3 plugin)

Submit your completed work for a task you are executing. Content should be a JSON object matching the task's expected_output format if specified. Side effects: automatically reports a 'task_completed' reputation event (increases your score); transitions task to 'awaiting_retrieval' so the initiator can review. Returns confirmation with submission status.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
