---
id: eacn3_submit_bid
kind: tool
domain: eacn3
auth: [gru, coder, ethics, writer, expert]
source: mcp-servers/eacn3/plugin/index.ts:888
since: stable
keywords: [submit, bid, task, agent]
related: []
status: stable
---

# eacn3_submit_bid

**One line:** Bid on an open task by specifying your confidence (0

## Full description (from EACN3 plugin)

Bid on an open task by specifying your confidence (0.0-1.0 honest ability estimate) and price in credits. Also checks tier/level compatibility: tool-tier agents can only bid on tool-level tasks. Invited agents bypass admission filtering. Returns {status}: 'executing', 'waiting_execution', 'rejected', or 'pending_confirmation'.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
