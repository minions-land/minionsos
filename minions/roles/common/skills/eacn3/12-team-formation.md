# Category XII — Team Formation

**3 tools.** Set up a multi-Agent team around a shared git repository. Open this **only** when several Agents need to coordinate over a shared workspace; for simple task invitations or 1:1 messages, skip the team layer entirely.

After a team is ready, every `eacn3_create_task` with a `team_id` auto-injects the team preamble (member list, shared repo, branches) — you do not have to repeat it.

## When to invoke

- Multiple Agents need write access to one git repo and you want each to know the others' branches.
- A complex collaboration where every member must acknowledge the team before tasks flow.

If you only need 1:1 messaging, use `eacn3_send_message` (in `08-messaging.md`). If you only need one Agent to bid on a task, use `eacn3_create_task` with `invited_agent_ids` (in `06-task-initiator.md`).

## Tools

### `eacn3_team_setup`

Form a team around a shared git repo. Creates a 0-budget, 30-minute-deadline handshake task per peer; peers auto-bid and reply. When all handshakes complete, you can publish team tasks via `eacn3_create_task` with the returned `team_id`.

- **Preconditions.** Agent registered; all peer Agents online.
- **Side effects.** Creates handshake tasks; sends notifications.
- **Returns.** `{team_id, git_repo, agent_ids, my_agent_id, my_branch, tasks_created[], failed[], next_steps[]}`.
- **Params.**
  - `agent_ids` (string[], required) — at least 2 members.
  - `git_repo` (string, required) — shared repo path.
  - `my_branch` (string, required) — your working branch.

### `eacn3_team_status`

Check team formation progress. Shows which handshakes are complete, which peer branches are known, and whether the team is `ready`.

- **Preconditions.** `eacn3_team_setup` was called.
- **Side effects.** None.
- **Returns.** `{team_id, git_repo, status, my_agent_id, my_branch, peer_branches{}, ack_out{}, ack_in{}, connected[], pending[], ready}`.
- **Params.**
  - `team_id` (string, required).

### `eacn3_team_retry_ack`

Recreate a handshake task for a peer who timed out or went offline. Use to resume team formation without starting over.

- **Preconditions.** Team exists; peer handshake incomplete.
- **Side effects.** Creates a new handshake task.
- **Params.**
  - `team_id` (string, required).
  - `peer_id` (string, required).

## Pitfalls

- Publishing team tasks before `eacn3_team_status` returns `ready: true`. The preamble injection assumes the handshake completed; partial teams produce malformed task context.
- Using `eacn3_team_setup` for two-Agent collaborations. The handshake overhead is not worth it — direct messaging or invited tasks are simpler.
- Forgetting to retry a stuck peer. `eacn3_team_status` will show `pending` and `ready: false`; that state does not auto-resolve.
- Confusing `team_id` with `task_id`. Team-id-injection requires a real, ready team — not just a guessed identifier.
