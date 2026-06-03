---
id: mos_await_events
kind: tool
domain: runtime
auth: [gru, expert, ethics]
source: minions/tools/mcp/runtime_tools.py:74
since: stable
keywords: [await, events, wake, drain, idle, eacn, loop]
related: [mos_noter_wait, mos_unread_summary, mos_get_events, eacn3_await_events]
status: stable
---

# mos_await_events

**One line:** Default wake driver for every EACN-registered Role. Long-polls, drains on read, idle-checks at ~5 min.

## Signature
```py
mos_await_events() -> {
  events: [ { event_id, type, payload, suggested_tool, ... } ],
  delivered_to_agent_id: str,
  idle_check: bool,
}
```
No params. Project + agent_id come from env.

## Behaviour
- Long-polls project EACN for ~60 s.
- Drains all unread events on read (no double-consume).
- After ~5 min of silence: returns `idle_check=true` so you can think.
- Heartbeats automatically between polls — watchdog spots dead sessions.
- Each event carries `suggested_tool` — hint, not command.

## Cold-start pattern
```py
ev = mos_await_events()
if ev["idle_check"]:
    mos_draft_view(); continue
for e in ev["events"]:
    handle(e)
```

## Don't
- Don't call `eacn3_await_events` / `eacn3_get_events` / `eacn3_next` directly —
  bypasses suggested-tool annotations and the idle check.
- Don't busy-loop after `idle_check=true`. Compact or reset instead.
- Don't call `mos_get_events` to "double-check" — already drained.

## Noter exception
Noter is **not** on EACN. Use `mos_noter_wait` (3-min timer).
