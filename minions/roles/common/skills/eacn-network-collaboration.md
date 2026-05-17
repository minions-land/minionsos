---
slug: eacn-network-collaboration
summary: MinionsOS-specific rules for using EACN3 inside a project Role; defers the tool reference to eacn3-mcp.
layer: scheduling
tools:
version: 3
status: active
supersedes:
references: eacn3-mcp, eacn3-state-machines, eacn3-error-recovery
provenance: human
---

# Skill — EACN Network Collaboration (MinionsOS context)

Tells a MinionsOS Role how its host runtime constrains EACN3 usage. The full per-tool detail lives in `eacn3-mcp` (the entry) and the 12 category files under `minions/roles/common/skills/eacn3/`.

## When to invoke

Open this skill when you are a MinionsOS project Role about to touch EACN3 for the first time in a wake. It tells you which parts of the underlying tool surface apply to you, which parts the runtime handles on your behalf, and where to go for the full reference. For the host-neutral EACN3 tool reference, open `eacn3-mcp` and pick the matching category file.

## Structure

MinionsOS changes three things about how a Role relates to EACN3. Everything else is normal EACN3.

1. **Identity is pre-allocated.** Your `agent_id` has already been registered by `minions.lifecycle.role` before you woke up. Do not register a new one. Use the injected ID whenever a tool accepts `agent_id` / `sender_id` / `initiator_id`.
2. **Event draining is pre-wrapped.** Drive your event loop with `mos_await_events()`. It internally chains the 60-second `GET /api/events/{agent_id}` long-poll, drains the queue, and only returns when there is actionable content. Do not call `eacn3_get_events` / `eacn3_await_events` / `eacn3_next` yourself; that bypasses the wrapper and drops the suggested-action annotations.
3. **Task market is the collaboration bus.** Substantive Role-to-Role coordination happens as EACN3 tasks. Do not hide work intent in private files, host conversation, the Exploration DAG, or Gru context; publish a task or bid on the one you received.

## Procedure

### Default tool surface for a normal wake

- **Non-destructive reads (always safe):** `eacn3_get_task`, `eacn3_get_task_status`, `eacn3_list_open_tasks`, `eacn3_list_tasks`, `eacn3_get_messages`, `eacn3_list_sessions`, `eacn3_list_agents`, `eacn3_get_task_results`. Detail in `eacn3/05-task-queries.md` and `eacn3/08-messaging.md`.
- **Outgoing work:** `eacn3_send_message`, `eacn3_create_task`. Detail in `eacn3/06-task-initiator.md` and `eacn3/08-messaging.md`.
- **Task-market writes on a task you received:** `eacn3_submit_bid`, `eacn3_submit_result`, `eacn3_reject_task`, `eacn3_create_subtask`. Detail in `eacn3/07-task-executor.md`.
- **Initiator-only writes on tasks you published:** `eacn3_select_result`, `eacn3_close_task`, `eacn3_update_deadline`, `eacn3_update_discussions`, `eacn3_confirm_budget`, `eacn3_invite_agent`. Detail in `eacn3/06-task-initiator.md`.
- **Connection lifecycle:** Roles do not call `eacn3_connect` / `eacn3_disconnect` / `eacn3_heartbeat`. The host owns those. Detail in `eacn3/02-server-management.md` only if you are debugging the host.

### Receiving a task

For each event the latest `mos_await_events()` call returned:

1. Read the event and extract `task_id`.
2. Call `eacn3_get_task(task_id)` before deciding (non-destructive).
3. Check domains, deadline, expected output, budget, and whether the work fits your Role boundary.
4. If it fits, call `eacn3_submit_bid(task_id, confidence, price, agent_id)`.
5. If accepted, do or delegate the work inside your Role boundary.
6. Call `eacn3_submit_result(task_id, content, agent_id)` with concrete output, artifact pointers, evidence, commands run, and blockers.
7. Exit when the batch is done. MinionsOS wakes you again on the next event; there is no ACK step you perform.

Silence is acceptable for public tasks that clearly do not fit your Role — just exit when done with the events that do.

### Publishing a task

Any EACN-visible work Role may publish a Local EACN task with `eacn3_create_task`. Use your injected `agent_id` as `initiator_id`; tasks are not Gru-only. Noter normally observes rather than assigns.

- For targeted work: set `invited_agent_ids=[peer_role_agent_id]` and use the target Role's domains. Role agent IDs are normally the role names (`coder`, `experimenter`, `writer`, `reviewer`, `ethics`, `noter`, `expert-*`).
- For public work: omit `invited_agent_ids` and choose domains describing the needed capability.

Task descriptions should include: goal and why it is needed; inputs and artifact paths; constraints, Role boundary, and deadline; expected output shape; how success will be checked. Use `budget=0` for normal project-local collaboration unless the author or task says otherwise. Full field detail is in `eacn3/06-task-initiator.md`.

### Direct messages vs. tasks

Use `eacn3_send_message` for short clarification, status, acknowledgements, or blocker notes. Do not ask for repository edits, experiments, paper sections, reviews, or evidence audits by direct message — those deserve a task. See `eacn3/08-messaging.md`.

### Gru

Do not route ordinary in-project dependencies through Gru. Contact Gru only for cross-project relay, author-facing decisions, deadline or risk escalation, deadlock, or system repair.

## Pitfalls

- **Double-draining.** Calling `eacn3_get_events` / `eacn3_await_events` / `eacn3_next` directly bypasses `mos_await_events`, drops the suggested-action annotations, and may steal events the wrapper is mid-poll on. Always go through `mos_await_events`.
- **Re-registering.** Do not call `eacn3_register_agent`. Your identity is already on the network; a second registration creates a duplicate AgentCard and confuses routing.
- **Hiding work as side channels.** Host conversation, the Exploration DAG, and shared files are not EACN-visible. If another Role needs to act, publish a task or send a message — do not assume they will "see" your DAG node or file change.
- **Noter publishing work tasks.** Noter observes and reports; it should not assign work unless explicitly instructed.
- **Loading every category file at once.** The `eacn3/` files are progressive disclosure — open only the category that matches your current action. `eacn3-mcp` is the entry; use it.
