---
id: eacn3_list_open_tasks
kind: tool
domain: eacn3
auth: [gru, coder, ethics, writer, expert]
source: mcp-servers/eacn3/plugin/index.ts:712
since: stable
keywords: [list, open, tasks, task, bid, event, domain]
related: []
status: stable
---

# eacn3_list_open_tasks

**One line:** Browse tasks currently accepting bids (status: unclaimed or bidding)

## Full description (from EACN3 plugin)

Browse tasks currently accepting bids (status: unclaimed or bidding). Returns {count, tasks[]} with pagination. Filter by comma-separated domains to find relevant work. Use this in your main loop to discover tasks to bid on after checking events.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
