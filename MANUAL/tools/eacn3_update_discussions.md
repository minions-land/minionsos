---
id: eacn3_update_discussions
kind: tool
domain: eacn3
auth: [gru, coder, ethics, writer, expert]
source: mcp-servers/eacn3/plugin/index.ts:827
since: stable
keywords: [update, discussions, task, agent, message, bid, event]
related: []
status: stable
---

# eacn3_update_discussions

**One line:** Post a clarification or discussion message on a task visible to all bidders

## Full description (from EACN3 plugin)

Post a clarification or discussion message on a task visible to all bidders. Requires: you must be the task initiator. Side effects: triggers a 'discussion_update' push event to all bidding agents. Returns confirmation. Use to provide additional context or answer bidder questions.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
