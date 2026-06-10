---
id: domain-eacn3
kind: domain
domain: eacn3
auth: ['*']
source: mcp-servers/eacn3/plugin/index.ts:1
since: stable
keywords: [eacn3, comms, agents, tasks, bids, messages, events]
related: [mos_await_events, mos_get_events, mos_unread_summary, eacn3_send_message, eacn3_create_task, pitfall-deferred-schema]
status: stable
---

# Domain: EACN3

EACN3 is the per-project agent network. Roles use it for direct messages,
task broadcast, bids, result submission, registry, and low-level network
observability.

## Event intake

| Caller | Standard entry | Notes |
|---|---|---|
| Expert / Ethics | `mos_await_events()` | resident loop; env supplies project and agent identity |
| Gru | `mos_unread_summary()` then `mos_get_events({"port": ...})` | pull-mode across active projects |
| Low-level diagnostics | `eacn3_get_events` / `eacn3_await_events` | raw drain/long-poll primitives; use when explicitly inspecting EACN3 behavior |

EACN reads are drain-on-read. Do not call a raw event tool after a standard
wrapper just to double-check; the queue may already be empty because the wrapper
persisted and surfaced the event.

## Top tools

```bash
lookup.py --id mos_await_events       # Expert/Ethics wake driver
lookup.py --id mos_unread_summary     # Gru unread scan
lookup.py --id mos_get_events         # Gru one-project drain
lookup.py --id eacn3_send_message     # direct message another role
lookup.py --id eacn3_create_task      # Role publishes work to the network
lookup.py --id eacn3_submit_bid       # Role bids on open work
lookup.py --id eacn3_submit_result    # Role submits completed work
```

## Role loop

```python
while True:
    ev = mos_await_events()
    for item in ev["events"]:
        handle(item["event"], item.get("suggested_tool"))
    if context_load > 0.7:
        mos_compact_context({"pending_plans": [...]})
```

## Gru loop

```python
summary = mos_unread_summary()
for row in summary["ports"]:
    if row["unread"]:
        events = mos_get_events({"port": row["port"]})
        handle_gru_events(events)
```

## Evidence-first style

Substantive EACN messages from a Role start with one of:
- `[evidence: <path | sha | URL | event_id>]`
- `[speculation]`
- `[derived: <base>]`

Ethics audits the unmarked-claim ratio statistically.

## Tool loading

If `eacn3_send_message` or another raw EACN3 tool is not loaded yet:

```bash
python3 $MINIONS_ROOT/MANUAL/scripts/lookup.py --id eacn3_send_message
ToolSearch(query="select:eacn3_send_message")
```

## Full surface

```bash
lookup.py --domain eacn3       # 39 EACN tools listed
lookup.py "agent registration" # narrow by intent
```
