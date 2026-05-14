# Stage B Coherence — common eacn3-* cluster B + glue (9 skills)

Audit date: 2026-05-14
Auditor: Stage B internal coherence check
Files inspected: 9 (read-only)

## Bucket summary

| Skill | Bucket | Confidence |
|---|---|---|
| eacn3-network-overview | COHERENT | high |
| eacn3-reputation | COHERENT | high |
| eacn3-state-machines | COHERENT | high |
| eacn3-task-executor | COHERENT | high |
| eacn3-task-initiator | COHERENT | medium-high |
| eacn3-task-queries | COHERENT | high |
| eacn3-team-formation | COHERENT | high |
| delegate-heavy-task | COHERENT | high |
| eacn-network-collaboration | COHERENT | high |

Counts: COHERENT 9 / NEEDS POLISH 0 / NEEDS REWRITE 0 / STITCHED-TOGETHER 0.

No file in this Stage-B set reads as a 缝合怪. Every skill scopes itself to one cluster (or one rule-set, for the two glue files), front-loads its trigger, indexes tools before detail, and defers cross-cluster topics by explicit `references:` rather than duplicating prose. Minor cross-skill ripples noted at the end.

## Per-skill verdicts

### eacn3-network-overview — COHERENT

**Evidence:**
- Frontmatter `summary: Open first when you don't know which eacn3-* skill to use; routes by intent ... to the right tool cluster.`
- Routing table at L50-63 maps Intent → skill → tools (one row per cluster), then closes with `Load only the cluster you need.`

**Diagnosis:** This is a real router, not a stealth catalog. The body teaches five nouns (Server / Agent / Domain / Credit / Reputation) and references the two FSMs at a five-line summary level, then defers to `eacn3-state-machines` for transitions. The intent table is the load-bearing artifact and points outward instead of inlining tool params. The two-FSM mini-diagram (L36-42) is brief enough to count as orientation, not duplication.

**Action:** Keep as is. (Optional polish: the labels `accepted` and `submitted` in the L36-42 Bid FSM mini-diagram are slightly informal vs. the canonical `eacn3-state-machines` labels — see cross-skill issues below.)

### eacn3-reputation — COHERENT

**Evidence:**
- L18-19 `The normal case is a single read: call eacn3_get_reputation ... eacn3_report_event is for edge cases only ... do not duplicate them manually.`
- L34-39 small ASCII flow shows that `submit_result` / `reject_task` / deadline auto-report; manual `report_event` is a thin escape hatch.

**Diagnosis:** Two-tool cluster with a clear "one is the normal one, the other is for edge cases" framing. The skill explicitly prevents the worst pitfall (double-reporting) up front. No FSM redocumentation; defers admission math to `eacn3-network-overview`.

**Action:** Keep as is.

### eacn3-state-machines — COHERENT

**Evidence:**
- Frontmatter: `Open before any task-mutating tool call, or when debugging a 400 state-machine error`
- L93 onward: a single transition-table from Goal tool → required Task status → required Bid status → recovery move.

**Diagnosis:** Pure FSM authority. Two FSMs documented, then a recovery table. No tool parameter detail (correctly delegated to executor / initiator / queries). The skill is self-contained around the single concept of "is this transition legal".

**Action:** Keep as is.

### eacn3-task-executor — COHERENT

**Evidence:**
- L17-19 `Open this skill when a task_broadcast event arrives ... when you are already executing a task and need to decide how to close it out ... The initiator's tools live in eacn3-task-initiator.`
- The four tool subsections each follow the same Purpose / Inputs / Output / Side effect / Pitfalls shape.

**Diagnosis:** Bounded by "I'm the executor": four bid-FSM transitions. The ASCII diagram (L25-45) is the executor's slice of the bid FSM, not a redocumentation of the full FSM. Pitfalls section calls out the right traps (lying about confidence, using `reject_task` to "pause"). Minor: the diagram shows `eacn3_submit_result → awaiting_retrieval`, which is the Task-FSM state — see cross-skill note.

**Action:** Keep as is.

### eacn3-task-initiator — COHERENT (medium-high confidence)

**Evidence:**
- L23-32 `Three sub-phases of the initiator's role: Publish / Steer / Close out` with the eight tools binned across phases.
- L19-20 `If you are only bidding on someone else's task, use eacn3-task-executor instead.`

**Diagnosis:** Eight tools is the largest cluster in the set, but they all share one role (initiator) and the Phase A/B/C scaffold gives a reader a map. Pitfalls list is per-tool but cohesive (`Forgetting budget arithmetic`, `Treating get_task_results as idempotent`, `Using select_result as a query`, ...). Confidence is medium-high rather than high only because the cluster size pushes the upper bound of "one cluster" — but it does not split.

**Action:** Keep. Future option: if this skill grows further, the Phase C close-out tools (`get_task_results` / `select_result` / `close_task`) could spin out into a `eacn3-task-closeout` skill, but right now the unity is real.

### eacn3-task-queries — COHERENT

**Evidence:**
- L19 `An executor inspects a broadcast with eacn3_get_task before bidding. An initiator monitors progress with eacn3_get_task_status. A browsing Agent picks work with eacn3_list_open_tasks. An auditor or debugger walks the backlog with eacn3_list_tasks.`
- L23-35 ASCII grid axes "full ↔ minimal detail" and "open only ↔ any state" — clean 2×2 mental model.

**Diagnosis:** Four read-only tools, neatly differentiated by detail-level vs. scope. The pitfalls call out the right traps (initiator-gated `get_task_status`, `list_open_tasks` is not the event bus, `limit` clamp at 200). No mutation, no FSM duplication.

**Action:** Keep as is.

### eacn3-team-formation — COHERENT

**Evidence:**
- L19 `If you do not need shared-repo coordination, do not form a team — direct messaging or task invitations are simpler.`
- L73-75 "After the team is `ready`" subsection pivots to `eacn3_create_task(team_id=...)` and references `eacn3-task-initiator`.

**Diagnosis:** Tightly scoped to one feature: team handshake using the task market as transport. The skill explains the auto-handshake mechanism, then the diagnostic and retry tools, then the `team_id` injection. Pitfalls correctly flag the most common mistakes (skipping self in `agent_ids`, treating handshake tasks as work, hammering retries).

**Action:** Keep as is.

### delegate-heavy-task — COHERENT

**Evidence:**
- L18-23: a tight "When to invoke" list of decision criteria (cross-file refactor, test failure diagnosis, autonomous iteration loop).
- L26-31 procedure is three steps: call `codex`, fall back on `CODEX_UNAVAILABLE` / `CODEX_ERROR`, review.

**Diagnosis:** Decision-oriented and short (50 lines). Does not turn into a codex-bridge implementation tutorial; does not list every codex tool parameter; only flags the few overrides a caller might want. The fallback path is one line. This is exactly the "when, not how-to-build" framing the audit asked for.

**Action:** Keep as is.

### eacn-network-collaboration — COHERENT

**Evidence:**
- L19 `For the full, host-neutral EACN3 tool reference, open eacn3-network-overview and follow its router.`
- L33-36 default tool surface lists tool names but each line ends with `See eacn3-task-queries, eacn3-messaging.` etc. — pointers, not redocumentation.

**Diagnosis:** This is the glue skill that was most at risk of becoming stitched-together (MinionsOS rules + EACN3 tool docs). It avoids that cleanly. The body identifies exactly the three things MinionsOS changes (pre-allocated identity, pre-drained events, task-market-as-bus) and then gives tight procedures for receive/publish/DM/Gru. Tool names appear in the body, but every cluster reference is a pointer to a sister skill rather than inline tool docs.

**Action:** Keep as is.

## Cross-skill issues

These are minor consistency concerns, not coherence failures within any single file.

1. **Bid-FSM terminal label drift between mini-diagrams.** `eacn3-network-overview` L40-42 writes the bid FSM as `... → waiting_subtasks → submitted OR → pending_confirmation (over-budget)`. `eacn3-state-machines` uses the canonical labels `rejected / waiting_execution / executing / waiting_subtasks / submitted / pending_confirmation`. `eacn3-task-executor` L25-45 draws the executor's slice ending in `eacn3_submit_result → awaiting_retrieval`, which is the *Task* FSM state, not a Bid state — for the executor this is fine because it is the visible result of submitting, but a strict reading collides with state-machines saying the Bid moves to `submitted`. None of these contradict behaviour, but a future polish pass could harmonise the three diagrams.

2. **Reputation arithmetic appears in three places.** `confidence × reputation ≥ threshold` is mentioned in `eacn3-network-overview` (L73), `eacn3-task-executor` (L56), and `eacn3-reputation` (L32). All three statements are consistent and each is locally load-bearing — overview teaches it, executor warns about it as an admission gate, reputation skill explains the gate semantics. This is reinforcement rather than duplication; flag only because the audit asked to watch for diverging guidance, and there is none.

3. **No tool is documented in two skills with conflicting advice.** Every tool has exactly one canonical home: `eacn3_submit_bid` lives in task-executor, `eacn3_create_task` in task-initiator, etc. Sister skills name tools but only as cross-references.

4. **`eacn-network-collaboration` does not redocument tools.** It cites tools by name and links to the canonical cluster. The audit's stated risk ("eacn-network-collaboration re-documenting tools that already live in eacn3-* siblings") does not materialise here.

5. **`eacn3-network-overview` does not duplicate other skills' content.** Its 5-noun model + 2-FSM blurb + intent table is the routing job; per-tool detail is left to the cluster skills. The audit's stated risk ("network-overview pretending to route but actually duplicating") does not materialise.

6. **`delegate-heavy-task` is purely decision content.** No codex-bridge implementation tutorial leaks in. The audit's stated risk does not materialise.

## Summary

All 9 files in this Stage-B set read as single coherent pieces. The progressive-disclosure design holds: `eacn3-network-overview` actually routes, `eacn3-state-machines` is the FSM authority and the other skills cite it, `eacn-network-collaboration` defers tool reference rather than duplicating it, and `delegate-heavy-task` stays a decision skill. The three cross-skill ripples above are wording-level, not conceptual.
