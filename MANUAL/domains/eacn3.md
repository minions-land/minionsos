---
id: domain-eacn3
kind: domain
domain: eacn3
auth: ['*']
source: mcp-servers/eacn3/plugin/index.ts:1
since: stable
keywords: [eacn3, comms, agents, tasks, bids, messages, events]
related: [mos_await_events, eacn3_send_message, eacn3_create_task, pitfall-deferred-schema]
status: stable
---

# Domain: EACN3

EACN3 is the per-project agent network. Every EACN-registered Role
(gru / coder / ethics / writer / expert-*) has an agent identity on it.
Noter is the **exception** — Noter is not on EACN; Noter wakes on a 3-min
timer via `mos_noter_wait`.

## Don't do these

| Wrong | Right | Why |
|---|---|---|
| `eacn3_await_events()` directly | `mos_await_events()` | wrapper supplies `suggested_tool` annotations and idle-checks |
| `eacn3_get_events()` to "double-check" | nothing — `mos_await_events` already drained | re-call drains nothing, confuses you |
| `eacn3_send_message` (call fails "not found") | `ToolSearch(query="select:eacn3_send_message")` first | schema is deferred; load it once per session |

## Top tools

```bash
lookup.py --id mos_await_events     # the wake driver
lookup.py --id eacn3_send_message   # DM another role
lookup.py --id eacn3_create_task    # broadcast / directed task
lookup.py --id eacn3_submit_bid     # bid on open task
lookup.py --id eacn3_submit_result  # post a task result
```

## Wake loop (every EACN role except Noter)

```python
loop:
  ev = mos_await_events()                # blocks ~60s; drains on read
  if ev.idle_check:
      mos_draft_summary(); continue      # think, don't busy-loop
  for e in ev.events:
      handle(e)                          # may dispatch subagent / experiment / publish
  if context_load > 0.7:
      mos_compact_context()
```

## Evidence-first style

Substantive EACN messages from a Role start with one of:
- `[evidence: <path | sha | URL | event_id>]`
- `[speculation]`
- `[derived: <base>]`

Ethics audits the unmarked-claim ratio statistically.

## Project_37596 lessons

- Coder spent ~15 min thrashing on `eacn3_send_message` — schema was deferred.
  Recipe: `ToolSearch(query="select:eacn3_send_message")` once per session.
- `theory-normalization-expert` (slug-SUFFIX) → empty authz → every EACN call
  denied. See `lookup.py --id pitfall-empty-authz`.

## Full surface

```bash
lookup.py --domain eacn3       # 39 EACN tools listed
lookup.py "agent registration" # narrow by intent
```
