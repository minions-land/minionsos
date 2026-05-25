---
id: eacn3_confirm_budget
kind: tool
domain: eacn3
auth: [gru, coder, ethics, writer, expert]
source: mcp-servers/eacn3/plugin/index.ts:835
since: stable
keywords: [confirm, budget, task, bid, event, balance]
related: []
status: stable
---

# eacn3_confirm_budget

**One line:** Approve or reject a bid that exceeded your task's budget, triggered by a 'bid_request_confirmation' event

## Full description (from EACN3 plugin)

Approve or reject a bid that exceeded your task's budget, triggered by a 'bid_request_confirmation' event. Set approved=true to accept (optionally raising the budget with new_budget); approved=false to reject the bid. Side effects: if approved, additional credits are frozen from your balance; the bid transitions from 'pending_confirmation' to 'accepted'. Returns updated task status.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
