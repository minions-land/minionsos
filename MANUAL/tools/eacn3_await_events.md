---
id: eacn3_await_events
kind: tool
domain: eacn3
auth: [gru, coder, ethics, writer, expert]
source: mcp-servers/eacn3/plugin/index.ts:1081
since: stable
keywords: [await, events, agent, event]
related: []
status: stable
---

# eacn3_await_events

**One line:** Fetch events from the network with a configurable wait time

## Full description (from EACN3 plugin)

Fetch events from the network with a configurable wait time. First checks locally buffered synthetic events, then does a single long-poll to the network. Returns {event, suggested_action, params} or {timeout: true} if nothing happened. Prefer this over eacn3_get_events for reactive agent loops.

## See also
Use `mos_await_events` instead of `eacn3_await_events` / `eacn3_get_events` /
`eacn3_next` directly — the wrapper supplies suggested-tool annotations and
the Gru watchdog. See `domains/eacn3.md` for the wake-loop pattern.
