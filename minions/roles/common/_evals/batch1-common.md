# Batch: common (EACN3 manual + collab)

## Per-skill grades

| slug | summary | trigger | procedure | pitfalls | structure | mean | verdict |
|---|---|---|---|---|---|---|---|
| eacn-network-collaboration | 4 | 4 | 5 | 5 | 4 | 4.4 | KEEP |
| eacn3-network-overview | 3 | 4 | 5 | 4 | 4 | 4.0 | TUNE |
| eacn3-state-machines | 4 | 5 | 5 | 5 | 5 | 4.8 | KEEP |
| eacn3-event-loop | 4 | 4 | 5 | 5 | 5 | 4.6 | KEEP |
| eacn3-bootstrap | 4 | 4 | 5 | 5 | 5 | 4.6 | KEEP |
| eacn3-agent-lifecycle | 4 | 4 | 5 | 5 | 5 | 4.6 | KEEP |
| eacn3-discovery | 4 | 4 | 5 | 5 | 5 | 4.6 | KEEP |
| eacn3-task-queries | 4 | 4 | 5 | 5 | 5 | 4.6 | KEEP |
| eacn3-task-initiator | 4 | 4 | 5 | 5 | 5 | 4.6 | KEEP |
| eacn3-task-executor | 4 | 4 | 5 | 5 | 5 | 4.6 | KEEP |
| eacn3-messaging | 4 | 4 | 5 | 5 | 5 | 4.6 | KEEP |
| eacn3-reputation | 4 | 4 | 5 | 5 | 5 | 4.6 | KEEP |
| eacn3-economy | 4 | 3 | 4 | 4 | 4 | 3.8 | TUNE |
| eacn3-team-formation | 4 | 3 | 5 | 5 | 5 | 4.4 | TUNE |

---

## Per-skill notes

### eacn-network-collaboration
- **Verdict:** KEEP
- **Strengths:** The three MinionsOS-specific constraints (pre-allocated identity, pre-drained queue, task market as collaboration bus) are crisp and actionable. Pitfalls are concrete and directly prevent the most common failure modes.
- **Issues:**
  - Summary says "defers the tool reference to eacn3-network-overview" — this describes the file's relationship to another skill, not the trigger or outcome a role needs to decide "open this now". A role scanning summaries cannot tell from this whether it applies to them.
  - "Open this skill when you are a MinionsOS project Role about to touch EACN3 for the first time in a wake" — "for the first time in a wake" is an odd qualifier; the constraints apply every wake, not just the first.
- **Recommended action:** Rewrite summary to state the trigger and outcome: e.g. "MinionsOS-specific EACN3 constraints for project Roles: pre-allocated identity, pre-drained queue, task-market collaboration rules."

---

### eacn3-network-overview
- **Verdict:** TUNE
- **Strengths:** The routing table (intent → skill → tools) is the best feature — it makes this a genuine decision node rather than a content dump. The five-noun / two-FSM framing is compact and accurate.
- **Issues:**
  - Summary reads "Routing entry for the EACN3 network; points to the tool-cluster skill for your next action." — no trigger signal. A role cannot tell from this whether to open it before or after connecting, or only when lost.
  - The `## When to invoke` section lists every possible EACN3 action ("publishing or bidding on a task, sending an agent-to-agent message, querying reputation or balance, forming a team...") — this is effectively "open me whenever you use EACN3", which is too broad to be a decision criterion. It should instead say: open this when you do not already know which cluster skill to open.
  - The `## Structure` section contains a full conceptual primer (five nouns, two FSMs, event rhythm) that is useful but makes this file heavier than a pure router should be. A role that already knows EACN3 pays context cost for content it does not need.
- **Recommended action:** Tighten summary to "Open first when you don't know which eacn3-* skill to use; routes by intent to the right tool cluster." Trim `## When to invoke` to one sentence. Consider moving the five-noun primer to a separate `eacn3-concepts.md` so the router stays thin.

---

### eacn3-state-machines
- **Verdict:** KEEP
- **Strengths:** The FSM diagrams are precise and directly answer "is this transition legal right now?" The procedure table (goal tool → required states → recovery) is the most immediately executable reference in the batch. Pitfalls catch real, non-obvious failure modes (`pending_confirmation` as a side-branch, `no_one` vs `rejected` confusion).
- **Issues:**
  - Summary "Task and Bid finite-state machines for EACN3; reference for which transitions are reachable." is accurate but does not include a trigger signal. A role scanning summaries cannot tell when to open this vs. just reading the overview.
  - Minor: the `## Structure` section is doing double duty as both structure description and the primary reference content (the FSM diagrams). This is fine given the file's purpose, but the section header is slightly misleading — the diagrams are the procedure, not just the structure.
- **Recommended action:** Prepend trigger to summary: "Open before any task-mutating tool call or when debugging a 400 state-machine error; shows Task and Bid FSM transitions."

---

### eacn3-event-loop
- **Verdict:** KEEP
- **Strengths:** The three-tool comparison table and the urgency ranking table are immediately actionable. The MinionsOS double-drain warning is prominent and correctly placed in both `## When to invoke` and `## Pitfalls`. The `eacn3_next` idle-prompt behavior is explained in a way that prevents busy-waiting.
- **Issues:**
  - Summary "Event-queue draining tools and the event taxonomy that drives reactive agent loops on EACN3." — no trigger signal. Does not tell a MinionsOS role whether to open this (they should not, per the file itself).
  - The `## When to invoke` section correctly warns MinionsOS roles away, but the summary does not reflect this. A role scanning summaries might open this unnecessarily.
- **Recommended action:** Update summary to: "Drain tools (get/await/next) and event taxonomy for standalone EACN3 loops; MinionsOS roles do NOT call these — queue is pre-drained."

---

### eacn3-bootstrap
- **Verdict:** KEEP
- **Strengths:** The three-layer ASCII diagram (diagnostics / session lifecycle / identity reuse) maps cleanly to the tools. Each tool entry has a clear "use when" and "side effect" that prevents misuse. Pitfalls are specific and consequence-aware (e.g. "active tasks held by this Agent will time out and reduce reputation").
- **Issues:**
  - Summary "Connect, heartbeat, inspect, and disconnect a Server session on EACN3, plus claim previously-registered Agents." is accurate but reads as a tool list, not a trigger+outcome. A role cannot tell from this whether they need it right now.
  - "If a host runtime (e.g. MinionsOS lifecycle) already manages the connection for you, the only call you may still need is `eacn3_health` for diagnostics" — this is the right guidance but is buried in `## When to invoke` body text rather than being the lead sentence.
- **Recommended action:** Reorder `## When to invoke` to lead with the MinionsOS case ("In MinionsOS, only `eacn3_health` is typically needed — the host manages the session"). Update summary to include trigger: "Session connect/disconnect/heartbeat tools; in MinionsOS only eacn3_health is typically needed."

---

### eacn3-agent-lifecycle
- **Verdict:** KEEP
- **Strengths:** The ASCII diagram showing the three paths from `eacn3_connect` (new / resume / pre-registered) is clear. The `eacn3_register_agent` parameter table is thorough without being overwhelming. Pitfalls catch real traps (`tier` immutability, `unregister` being destructive).
- **Issues:**
  - Summary "Register, inspect, update, and unregister Agent identities on EACN3, and list the Agents on your Server." is a tool list, not a trigger. A MinionsOS role (which should not register) cannot tell from this that the file is mostly irrelevant to them.
  - "Host runtimes that pre-register Agents (e.g. MinionsOS) handle creation for you; in that case you normally only need `eacn3_get_agent` and `eacn3_list_my_agents`." — correct but buried mid-paragraph.
- **Recommended action:** Lead `## When to invoke` with the MinionsOS case. Update summary: "Manage Agent identities; in MinionsOS only eacn3_get_agent / eacn3_list_my_agents are typically needed — registration is pre-done."

---

### eacn3-discovery
- **Verdict:** KEEP
- **Strengths:** The two-column comparison (gossip-DHT-bootstrap vs. flat registry) is the clearest structural explanation in the batch. The choice table (you want X → call Y) is immediately usable. Pitfalls are specific and non-obvious (gossip is per-Agent, `list_agents` is not a liveness check).
- **Issues:**
  - Summary "Find other Agents on EACN3 by domain, using gossip-DHT-bootstrap discovery or a flat registry browse." — accurate but no trigger. A role cannot tell from this whether to open it before publishing a task or only when they need to find a peer.
  - `## When to invoke` is good but lists three separate triggers without prioritizing; the most common case (before publishing a task) should lead.
- **Recommended action:** Minor summary tweak: "Find Agents by domain before publishing a task or sending a direct message; two tools: gossip-first discover vs. paginated list."

---

### eacn3-task-queries
- **Verdict:** KEEP
- **Strengths:** The 2×2 matrix (single/browsing × full/minimal) is the clearest structural diagram in the batch for its size. The "not suitable for executor work-finding" note on `list_tasks` prevents a common misuse. Pitfalls are specific and consequence-aware.
- **Issues:**
  - Summary "Read-only task queries on EACN3 — fetch one task, check a task's status, list open tasks, or browse any task by filter." — accurate but no trigger. Does not tell a role when to open this vs. just calling `eacn3_get_task` directly.
  - `eacn3_get_task_status` is initiator-gated (403 for non-initiators) — this is mentioned in pitfalls but should also appear in the tool's procedure entry to prevent the call being made at all.
- **Recommended action:** Add "initiator-only, returns 403 for others" to the `eacn3_get_task_status` procedure entry. Summary tweak: "Safe read-only task tools — open before any mutating call to inspect task state without side effects."

---

### eacn3-task-initiator
- **Verdict:** KEEP
- **Strengths:** The three-phase structure (Publish / Steer / Close out) maps directly to the task lifecycle and makes the file easy to navigate mid-task. The escrow lifecycle note (freeze → transfer → refund) is the clearest economy explanation in the batch. Pitfalls are specific and consequence-aware.
- **Issues:**
  - Summary "Publish and steward a task on EACN3 as initiator — create, invite, clarify, extend, confirm budget, collect results, select a winner, close." — this is a complete tool list masquerading as a summary. At 130 chars it fits the 200-char limit but gives no trigger signal.
  - "Publishing without `domains` and without `invited_agent_ids`" pitfall is critical but listed last; it should be first or second since it results in a task that silently receives no bids.
- **Recommended action:** Reorder pitfalls to put the no-routing trap first. Summary tweak: "Open when publishing a task or handling bid_request_confirmation / task_collected events as the task initiator."

---

### eacn3-task-executor
- **Verdict:** KEEP
- **Strengths:** The Bid-FSM flow diagram in `## Structure` is the clearest per-tool state diagram in the batch. Each tool entry has explicit preconditions and side effects. Pitfalls are specific and consequence-aware, especially the `confidence` honesty note and the `reject_task` reputation cost.
- **Issues:**
  - Summary "Bid on, execute, deliver, reject, or delegate EACN3 tasks as the executor role." — accurate but no trigger. A role receiving a `task_broadcast` event cannot tell from this whether to open it or just call `eacn3_submit_bid` directly.
  - "Lying about `confidence`" pitfall is the most important one (it compounds over time) but is listed first without a concrete symptom. Adding "symptom: bid admission rate falls over successive tasks even when work quality is high" would make it more actionable.
- **Recommended action:** Add symptom to the `confidence` pitfall. Summary tweak: "Open when a task_broadcast event arrives or when deciding how to close out a task you are executing."

---

### eacn3-messaging
- **Verdict:** KEEP
- **Strengths:** The three-layer delivery diagram (local → A2A → relay) is unique in the batch and explains behavior that would otherwise be invisible. The "not for substantive work" boundary is stated clearly and early. Pitfalls are specific and non-obvious (history is per-session local state, not network-authoritative).
- **Issues:**
  - Summary "Direct agent-to-agent messaging on EACN3 — send, read history, list active sessions." — accurate but no trigger. Does not tell a role when messaging is appropriate vs. a task.
  - "Messages you sent are preserved; messages the peer sent to you depend on whether you drained them before shutdown" — this is a subtle asymmetry that deserves its own pitfall entry rather than being buried in the "Reading history as authoritative" pitfall.
- **Recommended action:** Split the session-restart asymmetry into its own pitfall. Summary tweak: "Open for short clarifications, acknowledgements, or pre-bid questions; not for deliverables — use tasks for those."

---

### eacn3-reputation
- **Verdict:** KEEP
- **Strengths:** The auto-vs-manual reporting table is the clearest explanation of when `eacn3_report_event` is appropriate. The `confidence × reputation ≥ threshold` formula with a worked example is the best quantitative pitfall in the batch. The "over-weighting new Agents" pitfall is a genuine nuance.
- **Issues:**
  - Summary "Read or manually report reputation events for any Agent on EACN3; reputation gates bid admission." — accurate but no trigger. A role cannot tell from this whether to open it before bidding or only when something goes wrong.
  - `eacn3_report_event` use cases ("rare, usually only in test harnesses") suggest this tool is almost never needed by a normal role. The `## When to invoke` section should lead with "you almost certainly do not need `eacn3_report_event`" to prevent misuse.
- **Recommended action:** Lead `## When to invoke` with the normal case (just use `eacn3_get_reputation`; `eacn3_report_event` is for edge cases). Summary tweak: "Check a peer's reputation score before inviting or bidding; manual event reporting is for edge cases only."

---

### eacn3-economy
- **Verdict:** TUNE
- **Strengths:** The account diagram (available / frozen) and the lifecycle bullet list (create → confirm → select → close → timeout) are clear and complete. The "frozen is not spendable" pitfall is the most important one and is listed first.
- **Issues:**
  - Summary "Inspect an Agent's credit balance (available + frozen) and deposit EACN credits." — accurate but no trigger. A role cannot tell from this when to open it.
  - `## When to invoke` says "Executors only rarely need it — bid prices are paid *from* the task escrow, not the executor's balance." This is correct but the implication (executors can skip this file entirely) should be stated more directly: "If you are an executor, you do not need this skill."
  - The trigger coverage is weak: "before publishing a task" and "when diagnosing a 402" are the only two triggers listed. Missing: before calling `eacn3_confirm_budget` (initiator needs to know if they can cover the top-up).
- **Recommended action:** Add `eacn3_confirm_budget` as a trigger. State explicitly that executors can skip this file. Summary tweak: "Open before eacn3_create_task or eacn3_confirm_budget to verify available credits; executors rarely need this."

---

### eacn3-team-formation
- **Verdict:** TUNE
- **Strengths:** The handshake flow diagram is clear and the "auto-handled by plugin" note prevents manual interference. The `TeamInfo` field list is complete. Pitfalls are specific and consequence-aware (wrong `git_repo`, handshake deadline expiry).
- **Issues:**
  - Summary "Form a team of EACN3 Agents around a shared git repository via ACK-tracked handshake tasks." — accurate but no trigger. A role cannot tell from this whether team formation is relevant to their current situation.
  - `## When to invoke` says "If you do not need shared-repo coordination, do not form a team — direct messaging or task invitations are simpler." This is good guidance but should be the lead sentence, not the second sentence.
  - The trigger coverage is weak: "when several Agents need to collaborate around a shared git repo" is the only trigger. Missing: when `eacn3_create_task` with `team_id` is needed (which requires the team to already be `ready`), and when a peer is stuck in `pending`.
  - "Hammering `eacn3_team_retry_ack`" pitfall says "retrying every minute does not bring them back" but does not say what to do instead beyond "message them or reschedule" — the reschedule path is unspecified.
- **Recommended action:** Lead `## When to invoke` with the negative case. Add "team must be ready before eacn3_create_task with team_id" as a trigger. Summary tweak: "Open only when multiple Agents need shared git-repo coordination; skip for simple task invitations or direct messages."

---

## Batch-level observations

- **Summary quality is the weakest dimension across the batch.** 13 of 14 summaries describe what the file contains (tool list or concept name) rather than stating a trigger and outcome. A role scanning summaries to decide "do I need to open this right now?" gets almost no signal. The fix is consistent: prepend trigger condition + outcome to every summary.

- **MinionsOS context is inconsistently surfaced.** `eacn-network-collaboration` and `eacn3-event-loop` correctly warn MinionsOS roles away from tools the host handles. But `eacn3-bootstrap`, `eacn3-agent-lifecycle`, and `eacn3-reputation` bury the MinionsOS-specific guidance mid-paragraph. A MinionsOS role opening any of these files should see the host-managed constraint in the first two sentences of `## When to invoke`.

- **Procedure and pitfall quality is uniformly high.** Every file in the batch has numbered, tool-named, consequence-aware procedure entries and specific pitfalls with symptoms. This is the strongest dimension across the batch and should be treated as the house style.

- **Cross-skill redundancy is intentional and well-managed.** The double-drain warning appears in `eacn-network-collaboration`, `eacn3-event-loop`, and `eacn3-bootstrap` — appropriate given the severity of the failure. The `confidence × reputation` formula appears in both `eacn3-network-overview` and `eacn3-reputation` — acceptable given the overview's routing role.

- **Coverage gap: error recovery paths.** No skill covers what to do when an `eacn3_*` tool returns a non-400 error (network timeout, 503, plugin crash). The `eacn3-bootstrap` pitfall on "trusting the session after a lost endpoint" is the closest, but a role that hits a tool error mid-task has no guidance on whether to retry, reconnect, or escalate to Gru.

- **`eacn3-economy` and `eacn3-team-formation` are the two files most in need of tuning.** Both have weak trigger coverage and summaries that do not help a role decide whether to open them. Neither is wrong — they just need the same trigger-first treatment the stronger files already have.
