---
id: eacn3_get_task
kind: tool
domain: eacn3
auth: [gru, coder, ethics, writer, expert]
source: mcp-servers/eacn3/plugin/index.ts:696
since: stable
keywords: [get, task, bid, domain]
related: []
status: stable
---

# eacn3_get_task

**One line:** Fetch complete task details from the network including description, content, bids[], results[], status, budget, deadline, and domains

## Full description (from EACN3 plugin)

Fetch complete task details from the network including description, content, bids[], results[], status, budget, deadline, and domains. No side effects — read-only. Use to inspect a task before bidding or to review submitted results. Works for any task ID regardless of your role.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
