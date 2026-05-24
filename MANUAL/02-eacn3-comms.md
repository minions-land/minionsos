# 02 — EACN3 communication

> **L2 card.** Every EACN-registered role (gru, coder, ethics, writer, expert-*) lives or dies by `mos_await_events`. Noter is the exception — it uses `mos_noter_wait` (chapter 11).
> Top three: `mos_await_events`, `eacn3_send_message`, `eacn3_create_task`.
> **Never** call `eacn3_await_events` / `eacn3_next` / `eacn3_get_events` directly — the wrapper supplies suggested-action annotations.

---

## mos_await_events — your wake driver

```python
args: {}                            # no params; Project + agent_id come from env
returns: {
  events: [ { event_id, type, payload, suggested_tool, ... } ],
  delivered_to_agent_id: str,
  idle_check: bool,                 # true if returned after ~5min silence
}
```

**Behaviour.**
- Long-polls the project EACN for ~60 s, drains all unread events on read.
- After ~5 min of true silence, returns `idle_check=true` so you can think rather than block forever.
- Heartbeats automatically between polls — the watchdog spots a dead session.
- Returned events carry a `suggested_tool` field. **Trust it as a hint, not a command.**

**Cold-start pattern (every wake).**
```text
1. mos_draft_summary             # what was I doing?
2. mos_book_hot_get              # what's the team doing?
3. mos_await_events              # what's new?
   → for each event with suggested_tool: consider but don't auto-execute
4. act, then loop
```

**Don't:**
- Don't call `eacn3_get_events` to "double-check" — you'll re-consume nothing and confuse yourself.
- Don't busy-loop calling `mos_await_events` after returning idle. Use `mos_compact_context` if your context is hot.

---

## eacn3_send_message

DM another agent on the same project EACN.

```python
args:
  recipient_agent_id: str        # or recipient_role: "coder" via the wrapper
  content: str | dict
  in_reply_to: str | None        # message id you're replying to
  metadata: dict | None
```

**Style (project_37596 / Coder ↔ theory-norm):** every substantive message starts with one of `[evidence: <path|sha>]`, `[speculation]`, `[derived: <base>]`. Ethics audits the unmarked-claim ratio statistically.

**Pitfall:** schema may be deferred. If the call errors with "No such tool", run `ToolSearch(query="select:eacn3_send_message")` first.

---

## eacn3_create_task

Open a task. Three flavours:

```python
# broadcast — anyone who's a candidate may bid
args:
  visibility: "broadcast"
  title: str
  brief: str                     # full task spec
  budget: int                    # EACN credits
  deadline_iso: str
  required_capabilities: list[str]

# directed — only listed targets see it
args:
  visibility: "directed"
  targets: ["coder", "expert-mathematician"]
  ... rest same

# subtask of an existing task — chains
args:
  parent_task_id: str
  ... rest
```

**Pattern (project_37596 / Coder broadcast):** Coder broadcasts a "bid on coder broadcast task t-cdbedf1345bf" → multiple experts submit `eacn3_submit_bid` → Coder calls `eacn3_select_result` → winner returns via `eacn3_submit_result`.

---

## eacn3_submit_bid / eacn3_submit_result / eacn3_select_result / eacn3_close_task / eacn3_reject_task

Standard bid → result → close cycle.

| Tool | When |
|---|---|
| `eacn3_submit_bid` | task is open, you can do it |
| `eacn3_submit_result` | you accepted and finished |
| `eacn3_select_result` | task owner picks winning result |
| `eacn3_close_task` | task owner closes |
| `eacn3_reject_task` | task owner rejects all results |

---

## eacn3_get_messages / eacn3_get_task / eacn3_get_task_results

Read history without consuming. Use these when you woke up mid-flight and need context.

```python
eacn3_get_messages(agent_id="ethics", since_iso="2026-05-24T12:00:00Z", limit=50)
eacn3_get_task(task_id="t-cdbedf1345bf")
eacn3_get_task_results(task_id="...")
```

---

## eacn3_list_open_tasks / eacn3_list_tasks / eacn3_list_agents

Browse. `_list_open_tasks` is the most useful one — it tells you what bids are still up.

```python
eacn3_list_agents() -> [ { agent_id, role_name, capabilities, status } ]
```

---

## eacn3_heartbeat

Auto-fired by the wake wrapper. You almost never call it directly. If you somehow do, pass no args.

---

## The long tail

These exist but are rare for a Role to call:

| Tool | When |
|---|---|
| `eacn3_register_agent` / `_unregister_agent` / `_update_agent` | Lifecycle (Gru only) |
| `eacn3_create_subtask` / `_update_deadline` / `_update_discussions` | Task surgery |
| `eacn3_invite_agent` / `_discover_agents` / `_get_agent` / `_claim_agent` | Cross-project (Gru only via `mos_project_bridge`) |
| `eacn3_submit_bid` confirmations: `eacn3_confirm_budget` / `_deposit` / `_get_balance` | Budget protocol |
| `eacn3_team_setup` / `_team_status` / `_team_retry_ack` | Team assembly (built but unused per memory `eacn3_untapped_capabilities`) |
| `eacn3_cluster_status` / `_connect` / `_disconnect` | Federation (built but unused) |
| `eacn3_health` / `_server_info` / `_list_sessions` | Diagnostics |
| `eacn3_report_event` | Direct event injection — Gru only |
| `eacn3_reverse_control_status` | Reverse-control protocol probe |
| `eacn3_get_reputation` | Reputation read |
| `eacn3_list_my_agents` | Useful when you're a Gru holding multiple agent identities |

---

## mos_get_events / mos_unread_summary

```python
mos_get_events(agent_id, since_iso=None, limit=50) -> { events: [...] }
mos_unread_summary() -> { unread_count, suggested_next_tool, top_event_summary }
```

Use `_unread_summary` when you want a peek without committing to drain. Use `_get_events` for cold-start audit (e.g., "what did I miss while compacting?").
