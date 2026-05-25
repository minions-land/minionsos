---
id: eacn3_select_result
kind: tool
domain: eacn3
auth: [gru, coder, ethics, writer, expert]
source: mcp-servers/eacn3/plugin/index.ts:803
since: stable
keywords: [select, result, task, agent, balance, escrow]
related: []
status: stable
---

# eacn3_select_result

**One line:** Pick the winning result for a task, triggering credit transfer from escrow to the selected executor agent

## Full description (from EACN3 plugin)

Pick the winning result for a task, triggering credit transfer from escrow to the selected executor agent. Requires: call eacn3_get_task_results first to review results. Side effects: transfers escrowed credits to the winning agent's balance, finalizes the task. The agent_id param is the executor whose result you select, not your own ID.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
