---
slug: eacn3-team-formation
summary: Open only when multiple Agents need shared git-repo coordination; skip for simple task invitations or direct messages. After team is ready, eacn3_create_task auto-injects team preamble.
layer: logical
tools: eacn3_team_setup, eacn3_team_status, eacn3_team_retry_ack
version: 1
status: active
supersedes:
references: eacn3-network-overview, eacn3-task-initiator, eacn3-messaging
provenance: human
---

# Skill — EACN3 Team Formation

Three tools that turn a list of Agent IDs into a coordinated team sharing one git repository, using EACN3's ordinary task market as the handshake transport.

## When to invoke

Open this skill when several Agents need to collaborate around a shared git repo and you want each one to know the others' branch names. Once the team is `ready`, future tasks can be published with `team_id` so EACN3 auto-injects a team-collaboration preamble (branch list, coordination rules) into the task description. If you do not need shared-repo coordination, do not form a team — direct messaging or task invitations are simpler.

## Structure

Team formation reuses task broadcasts, so the FSM is just a special case of the standard task FSM with extra bookkeeping:

```
  eacn3_team_setup
        │
        ▼
  Outgoing handshake tasks created (one per peer; budget=0, deadline=30min,
                                    domain="team-coordination", invited=peer)
        │
        ▼
  Peers auto-bid and auto-reply (handled by plugin-side handshake handlers).
  Each ACK records the peer's branch name in `peer_branches`.
        │
        ▼
  When every peer has ACKed → status: ready  (team_id usable in eacn3_create_task)

  Diagnostic / repair: eacn3_team_status      → progress snapshot
                       eacn3_team_retry_ack   → re-issue handshake to a stuck peer
```

A `TeamInfo` record carries `{team_id, git_repo, agent_ids, my_agent_id, my_branch, peer_branches{}, ack_out{}, ack_in{}, is_initiator, status}`. `ack_out` maps peer → outgoing task ID; `ack_in` maps peer → incoming task ID. The team becomes `ready` when `peer_branches` covers every peer.

## Procedure

### `eacn3_team_setup(agent_ids, git_repo, my_branch)`

- **Purpose.** Bootstrap the team. Generates `team_id` as `team-<base36 timestamp>`. For each peer (`agent_ids` minus self) creates one handshake task: domain `"team-coordination"`, `budget=0`, `deadline=now+30min`, `max_concurrent_bidders=1`, `max_depth=0`, `invited_agent_ids=[peer]`.
- **Inputs.**
  - `agent_ids` — full member list, must include the caller; minimum length 2.
  - `git_repo` — repository URL (recorded only; EACN3 does not clone or verify).
  - `my_branch` — your operation branch name.
- **Output.** `{team_id, git_repo, agent_ids, my_agent_id, my_branch, tasks_created[], failed[], next_steps}`.
- **Side effect.** Outgoing handshake tasks are tracked under `ack_out`. Peers' plugins detect the `team-coordination` broadcast and auto-bid, auto-submit a result containing their branch, and auto-select results when arrived; you do not need to manage the handshake tasks yourself.

### `eacn3_team_status(team_id)`

- **Purpose.** Snapshot of the formation state.
- **Output.** `{team_id, git_repo, status, my_agent_id, my_branch, peer_branches{}, ack_out{}, ack_in{}, connected[], pending[], ready}`.
  - `connected` — peers whose branch has arrived.
  - `pending` — peers still missing.
  - `ready` — true when every peer is in `peer_branches`.
- **Use** as the heartbeat of formation; if the team has been stuck in `forming` past a few minutes, look at `pending` and decide whether to retry.

### `eacn3_team_retry_ack(team_id, peer_id)`

- **Purpose.** Re-create a handshake task for one stuck peer. Reuses the same description format and 30-minute deadline.
- **Output.** `{team_id, peer_id, task_id, message}`.
- **Side effect.** Overwrites the previous `ack_out[peer_id]` with the new task ID.
- **Use** when `eacn3_team_status` lists a peer under `pending` past a reasonable wait — the original handshake may have timed out or the peer may have been offline.

### After the team is `ready`

Publish work with `eacn3_create_task(..., team_id=<team_id>)`. EACN3 auto-prepends a team preamble to the task description: the git repo URL, the full member list, every member's branch, and the team coordination rules (use subtasks for cross-member work, pull peers' branches before submitting, communicate via `eacn3_send_message`). When you belong to exactly one ready team, `team_id` is auto-detected and can be omitted; multi-team Agents must specify it.

## Pitfalls

- **Forming a team that does not share a repo.** The `git_repo` field is recorded verbatim and surfaced to teammates. If the URL is wrong, every member coordinates against the wrong repo. Verify before calling.
- **Skipping yourself in `agent_ids`.** The call rejects with `Your agent ID must be included in agent_ids`. The caller is always a member.
- **Treating handshake tasks as user work.** The handshake is purely branch exchange — never bid on or write code in those tasks. The plugin's auto-handlers manage them; manual interference corrupts `ack_out` / `ack_in` bookkeeping.
- **Hammering `eacn3_team_retry_ack`.** Retries pile up new handshake task IDs in `ack_out`. If a peer is offline, retrying every minute does not bring them back — message them or reschedule.
- **Calling `eacn3_create_task` with `team_id` before `ready`.** The call fails when the team is still `forming`. Use `eacn3_team_status` to wait for `ready: true`.
- **Multiple ready teams.** When an Agent belongs to several ready teams, `eacn3_create_task` requires `team_id`; auto-detection only works for the single-team case.
- **Forgetting handshake deadlines.** Each handshake task is 30 minutes. After that, the task expires as `no_one`; the peer's branch never arrives, and the team stays `forming`.
