---
id: eacn3_await_events
kind: tool
domain: eacn3
auth: [gru, expert, ethics]
source: mcp-servers/eacn3/plugin/index.ts:1081
since: stable
keywords: [await, events, agent, event]
related: [mos_await_events, mos_get_events, mos_unread_summary, eacn3_get_events]
status: stable
---

# eacn3_await_events

**One line:** Raw EACN3 long-poll for one agent identity.

## Signature
```py
eacn3_await_events(args={
  "agent_id": str | None,
  "timeout_seconds": int | None,
  "event_types": [str] | None,
}) -> dict
```

## Args
- `agent_id`: optional; when omitted, EACN3 resolves the current agent id.
- `timeout_seconds`: optional wait window, clamped by the server.
- `event_types`: optional filter.

## Behaviour
- Checks locally buffered synthetic events first, then performs one network
  long-poll.
- Successful event returns include routing hints such as `suggested_tool`.
- Timeout returns a timeout-shaped result; it does not synthesize MinionsOS
  keepalive, Draft reminders, or context-pressure guidance.

## Standard wrappers
- Expert / Ethics resident loop: use `mos_await_events`.
- Gru project intake: use `mos_unread_summary` then `mos_get_events`.

## Use this when
- You are explicitly diagnosing raw EACN3 polling behavior.
- You need raw timeout semantics instead of the MinionsOS never-empty resident
  wake loop.
