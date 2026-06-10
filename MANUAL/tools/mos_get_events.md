---
id: mos_get_events
kind: tool
domain: runtime
auth: [gru]
source: minions/tools/mcp/runtime_tools.py:316
since: stable
keywords: [gru, events, unread, drain, eacn, pull, queue]
related: [mos_unread_summary, mos_await_events, eacn3_get_events]
status: stable
---

# mos_get_events

**One line:** Gru-only one-project event drain. Pulls Gru's EACN queue and mirrors it to disk.

## Signature
```py
mos_get_events(args={"port": int}) -> {
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
  "unread_remaining": int,
}
```

## Args
- `port`: active project port whose Gru queue should be drained.

## Behaviour
- Performs a non-blocking EACN read for the project-local `gru` agent.
- Appends drained events to `project_{port}/events/gru.jsonl` before return.
- Advances Gru's `last_seen` pointer after surfacing the unread tail.
- `count` can be zero; this is a pull tool, not a resident blocking loop.

## Use
```py
summary = mos_unread_summary()
for row in summary["ports"]:
    if row["unread"] > 0:
        events = mos_get_events({"port": row["port"]})
        handle(events)
```

## Don't
- Don't use this from Expert or Ethics; they use `mos_await_events`.
- Don't call raw `eacn3_get_events` after this just to verify the same queue.
