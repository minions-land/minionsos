---
id: mos_unread_summary
kind: tool
domain: runtime
auth: [gru]
source: minions/tools/mcp/runtime_tools.py:332
since: stable
keywords: [gru, unread, events, projects, eacn, queue, scan]
related: [mos_get_events, mos_await_events]
status: stable
---

# mos_unread_summary

**One line:** Gru-only unread scan across active projects. Pure read; does not drain.

## Signature
```py
mos_unread_summary() -> {
  "ports": [
    {"port": int, "name": str, "unread": int}
  ],
  "total_unread": int,
}
```

## Args
No args.

## Behaviour
- Reads active projects from the state store.
- Counts unread Gru events using each project's persisted `gru.last_seen`.
- Does not call EACN and does not modify queues or event logs.

## Use
```py
summary = mos_unread_summary()
if summary["total_unread"]:
    target = max(summary["ports"], key=lambda row: row["unread"])
    events = mos_get_events({"port": target["port"]})
```

## Don't
- Don't expect event payloads here; use `mos_get_events({"port": ...})`.
- Don't use this from Expert or Ethics; their resident loop is `mos_await_events`.
