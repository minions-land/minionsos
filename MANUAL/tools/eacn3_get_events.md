---
id: eacn3_get_events
kind: tool
domain: eacn3
auth: [gru, expert, ethics]
source: mcp-servers/eacn3/plugin/index.ts:1067
since: stable
keywords: [get, events, task, agent, message, bid, event, subtask, broadcast, drain]
related: [mos_await_events, mos_get_events, mos_unread_summary, eacn3_await_events]
status: stable
---

# eacn3_get_events

**One line:** Raw non-blocking EACN3 event drain for one agent identity.

## Signature
```py
eacn3_get_events(args={"agent_id": str | None}) -> {
  "ok": bool,
  "count": int,
  "events": [dict],
  "reverse_control": dict,
}
```

## Args
- `agent_id`: optional; when omitted, EACN3 resolves the current agent id.

## Behaviour
- Fetches pending network events and drains locally buffered synthetic events.
- Returns immediately; it does not long-poll.
- Reading is destructive at the EACN queue boundary.

## Standard wrappers
- Expert / Ethics wake loop: use `mos_await_events`.
- Gru project intake: use `mos_unread_summary` then `mos_get_events`.

## Use this when
- You are explicitly inspecting low-level EACN3 behavior.
- You need a one-shot raw drain and will not also call the MinionsOS wrapper on
  the same queue.
