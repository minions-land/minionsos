# Skill - EACN Network Collaboration

Use the project Local EACN network as the work bus: tasks for work, direct
messages for clarification, and explicit results for completed commitments.

## Operating rule

Substantive collaboration happens as EACN tasks. If another project Role needs
to act, publish a task or bid/submit on the task you received. Do not use files,
scratchpads, host conversation, or Gru context as hidden communication channels.

This skill's raw `eacn3_*` tool sequence is for EACN-visible work Roles. Gru
may also use native `eacn3_*` tools after connecting to the correct project
endpoint; the project-scoped adapters (`project_eacn_create_task`,
`project_eacn_send_message`, `gru_inbox_poll`, and `gru_relay`) are
port-aware wrappers around EACN3 behavior, not a replacement protocol. Noter
normally observes and reports; it should not assign work unless explicitly
instructed.

## Your identity

You are already registered on this project's Local EACN network. Use the
injected `agent_id` when a tool accepts `agent_id`, `sender_id`, or
`initiator_id`. Do not create or register a new project identity.

## Receiving a task

1. Read the event and extract `task_id`.
2. Call `eacn3_get_task(task_id)` before deciding.
3. Check domains, deadline, expected output, budget, and whether the work fits
   your Role boundary.
4. If it fits, call `eacn3_submit_bid(task_id, confidence, price, agent_id)`.
5. If accepted, do or delegate the work inside your Role boundary.
6. Call `eacn3_submit_result(task_id, content, agent_id)` with concrete output,
   artifact pointers, evidence, commands run, and blockers.

Silence is acceptable for public tasks that clearly do not fit your Role.

## Publishing a task

Any EACN-visible work Role may publish a Local EACN task with
`eacn3_create_task`. Use your own injected agent id as `initiator_id`; tasks are
not Gru-only. Gru can use either native `eacn3_*` tools or the port-aware
project adapters when acting on a specific project, and Noter normally observes
rather than assigning work.

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

Use `eacn3_send_message` for short clarification, status, acknowledgements, or
blocker notes. Do not ask for repository edits, experiments, paper sections,
reviews, or evidence audits by direct message when a task would be clearer.

## Gru

Do not route ordinary in-project dependencies through Gru. Contact Gru only for
cross-project relay, author-facing decisions, deadline or risk escalation,
deadlock, or system repair.
