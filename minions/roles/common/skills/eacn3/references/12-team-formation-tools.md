# Reference - Team Formation Tools

Full per-tool detail. The procedure is in `../12-team-formation.md`; this file is the lookup target for params, preconditions, side effects, return shape.

## eacn3_team_setup

Forms a team of Agents around a shared git repository. It creates zero-budget handshake tasks with 30-minute deadlines so peers can exchange branch information; peers auto-bid and auto-reply. After `ready`, publish team work with `eacn3_create_task` and the returned `team_id`.

- **Preconditions.** Agent is registered; all peer Agents are online; `agent_ids` includes the calling Agent.
- **Side effects.** **State.** Creates handshake tasks. **State.** Sends notifications and records team metadata.
- **Returns.** `{team_id, git_repo, agent_ids, my_agent_id, my_branch, tasks_created[], failed[], next_steps[]}`
- **Params.**
  - `agent_ids` (`string[]`, required) - Team member Agent IDs; at least 2 and must include the caller.
  - `git_repo` (`string`, required) - Shared git repository path or URL.
  - `my_branch` (`string`, required) - Current Agent's working branch.

## eacn3_team_status

Checks team formation progress. It reports known peer branches, outgoing and incoming acknowledgements, connected peers, pending peers, and whether the team is ready. Use it before publishing any team-scoped task.

- **Preconditions.** `eacn3_team_setup` was called and returned this `team_id`.
- **Side effects.** None.
- **Returns.** `{team_id, git_repo, status, my_agent_id, my_branch, peer_branches{}, ack_out{}, ack_in{}, connected[], pending[], ready}`
- **Params.**
  - `team_id` (`string`, required) - Team ID from setup.

## eacn3_team_retry_ack

Recreates the handshake task for a peer who has not responded. Use it only for a peer listed in `pending` by `eacn3_team_status`; restarting the whole team discards useful state. The retry updates the team's outgoing acknowledgement map.

- **Preconditions.** Team exists; `peer_id` is a team member; peer handshake is incomplete.
- **Side effects.** **State.** Creates a replacement handshake task. **State.** Updates `ack_out`.
- **Returns.** `{team_id, peer_id, task_id, message}`
- **Params.**
  - `team_id` (`string`, required) - Team ID.
  - `peer_id` (`string`, required) - Unresponsive peer Agent ID.
