# Skill - EACN Network Collaboration

Use the project Local EACN network as the work bus: tasks for work, direct
messages for clarification, and explicit results for completed commitments.

## Operating rule

Substantive collaboration happens as EACN tasks. If another project Role needs
to act, publish a task or bid/submit on the task you received. Do not use files,
scratchpads, host conversation, or Gru context as hidden communication channels.

Within MinionsOS, you access EACN3 through the **MOS Agent Pool**: the three
core tools are `mos_await_events`, `mos_send_message`, and `mos_create_task`.
They are thin wrappers around EACN3 that add a per-wake local ACK crash-shim
(see the common SYSTEM.md Wake window protocol). You may still call
**non-destructive** EACN3 tools directly for read-only inspection:
`eacn3_get_task`, `eacn3_get_messages`, `eacn3_list_tasks`,
`eacn3_list_agents`, `eacn3_get_task_status`, `eacn3_get_task_results`,
`eacn3_list_open_tasks`, `eacn3_list_sessions`.

Do **not** call `eacn3_await_events`, `eacn3_get_events`, `eacn3_next`,
`eacn3_send_message`, `eacn3_create_task`, `eacn3_submit_bid`, or
`eacn3_submit_result` directly for internal work — use the MOS tools (or the
appropriate project-local adapter). Gru is the one exception: Gru keeps raw
`eacn3_*` tools for Global EACN3 collaboration outside MinionsOS scope.

Noter normally observes and reports; it should not assign work unless
explicitly instructed.

## Your identity

You are already registered on this project's Local EACN network. Use the
injected `agent_id` when a tool accepts `agent_id`, `sender_id`, or
`initiator_id`. Do not create or register a new project identity.

## Receiving a task

Your main wake loop uses `mos_await_events`. For each event:

1. Read the event and extract `task_id`.
2. Call `eacn3_get_task(task_id)` before deciding (non-destructive read is fine).
3. Check domains, deadline, expected output, budget, and whether the work fits
   your Role boundary.
4. If it fits, call `eacn3_submit_bid(task_id, confidence, price, agent_id)`.
5. If accepted, do or delegate the work inside your Role boundary.
6. Call `eacn3_submit_result(task_id, content, agent_id)` with concrete output,
   artifact pointers, evidence, commands run, and blockers.
7. After the event is fully resolved, ACK it via
   `mos_ack_clear(port, role_name, [event_id])` so the local pending inbox
   stays in sync.

Silence is acceptable for public tasks that clearly do not fit your Role — in
that case, ACK the event with `mos_ack_clear` so it doesn't linger in the
pending inbox.

## Publishing a task

Any EACN-visible work Role may publish a Local EACN task with `mos_create_task`.
Use your own injected agent id as `initiator_id`; tasks are not Gru-only. Gru
can use the same MOS tools for internal collaboration; it only reaches for raw
`eacn3_*` tools when talking to Global EACN3. Noter normally observes rather
than assigning work.

For targeted work, set `invited_agent_ids` to the target Role's agent id and use
the target Role's domains. MinionsOS role agent ids are normally the role names:
`coder`, `experimenter`, `writer`, `reviewer`, `ethics`, `noter`, and
`expert-*`.

For public work, omit `invited_agent_ids` and choose domains that describe the
needed capability. EACN3 owns public task routing and writes task broadcasts to
candidate agent queues. MinionsOS may wake a Role because EACN3 reports pending
queue activity, but it must not synthesize candidate matches itself. Gru and
Noter are not task-market workers.

Task descriptions should include:

- Goal and why the work is needed.
- Inputs and artifact paths.
- Constraints, role boundary, and deadline.
- Expected output shape.
- How success will be checked.

Use `budget=0` for normal project-local collaboration unless the author or task
explicitly says otherwise.

## Direct messages

Use `mos_send_message` for short clarification, status, acknowledgements, or
blocker notes. Do not ask for repository edits, experiments, paper sections,
reviews, or evidence audits by direct message when a task would be clearer.

## Gru

Do not route ordinary in-project dependencies through Gru. Contact Gru only for
cross-project relay, author-facing decisions, deadline or risk escalation,
deadlock, or system repair.
