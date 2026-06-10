---
id: mos_await_events
kind: tool
domain: runtime
auth: [expert, ethics]
source: minions/tools/mcp/runtime_tools.py:73
since: stable
keywords: [await, events, wake, drain, idle, eacn, loop, keepalive]
related: [mos_unread_summary, mos_get_events, eacn3_await_events, eacn3_get_events]
status: stable
---

# mos_await_events

**One line:** Resident wake driver for Expert and Ethics. Blocks internally, returns only actionable events.

## Signature
```py
mos_await_events() -> {
  "count": int,
  "events": [
    {
      "event": dict,
      "suggested_action": str,
      "suggested_tool": str | None,
      "suggested_params": dict,
      "urgency": str,
    }
  ],
}
```
No params. Project + agent_id come from env.

## Behaviour
- Repeats 60 s EACN long-polls while the model is suspended.
- Drains on read and synchronously mirrors real events to disk before return.
- Returns `count > 0`: real EACN events, a synthetic `idle_check`, a synthetic
  `cold_start_hint`, a synthetic `context_pressure_compact`, or a synthetic
  `cache_keepalive`.
- Heartbeats automatically between polls so external monitors can see liveness.
- Each returned item carries `suggested_tool`; treat it as a routing hint.

## Cold-start pattern
```py
ev = mos_await_events()
for e in ev["events"]:
    event = e["event"]
    if event.get("type") == "cache_keepalive":
        # fixed ack path, then immediately call mos_await_events again
        continue
    handle(event, suggested_tool=e.get("suggested_tool"))
```

## Don't
- Don't use this from Gru. Gru uses `mos_unread_summary` and `mos_get_events`.
- Don't call raw `eacn3_await_events` / `eacn3_get_events` after this just to
  double-check; EACN reads are drain-on-read.
- Don't ignore `context_pressure_compact`; persist any pending plan before the
  scheduled compact lands.
