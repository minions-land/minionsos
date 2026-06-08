---
slug: evidence-pointer-sweep
summary: Audit [evidence: ...] / [derived: ...] markers on EACN messages and artifacts — confirm pointers resolve and content matches the claim, sample-based.
layer: logical
tools: eacn3_get_task, eacn3_get_messages, eacn3_send_message
version: 2
status: active
supersedes:
references: citation-authenticity-audit
provenance: human
---

# Skill — Evidence Pointer Sweep

The evidence-first EACN convention only has bite if pointers are audited. Sample broken / mismatched pointers and treat them as quiet hallucinations.

## When to invoke

- Once per project phase (e.g. after each successful experiment batch settles).
- Before formal review rounds, so the submission package does not carry
  silently broken pointers.
- After heavy refactoring or experiment regeneration — artifact paths may have moved.
- On request from Gru or the author, especially before a high-stakes decision.

## Structure

Pointer types and how to resolve:

| Pointer kind | Resolution check |
|---|---|
| Artifact path | File exists in project worktree; commit SHA via `git log --follow`; bundle reports cite real logs / CSVs / checkpoints |
| Commit SHA | SHA exists in project-worktree history; touched files are plausibly relevant |
| URL | HEAD-fetch confirms reachability; for academic URLs, defer citation-shaped cases to `citation-authenticity-audit` |
| EACN event id | `eacn3_get_task(task_id)` or `eacn3_get_messages(agent_id)` returns the claimed event with matching content |

Classifications: `verified`, `wrong_context` (resolves but does not support the claim), `broken` (does not resolve). Severity scales with claim stakes — one broken pointer in a chat message is a soft nudge; one under a camera-ready claim is a hard flag.

Outputs are drafted in `branches/ethics/report-evidence-sweep-<ts>.md` (per-Role counts + highest-severity broken list) and published to `branches/main/ethics/report-evidence-sweep-<ts>.md`; each hard flag is drafted as `branches/ethics/flag-<slug>.md` and published to `branches/main/ethics/flag-<slug>.md`.

## Procedure

1. **Collect pointers in scope.** Default sample window: last 50 EACN messages per role, or last 10 artifacts under a Role's write scope. For a specific handoff audit requested by Gru, take the full set of pointers in that handoff. Extract every `[evidence: ...]` and `[derived: ...]` marker with its enclosing claim and source (Role, event id, file path).
2. **Classify the pointer type and resolve it** per the table above.
3. **Cross-check the claim.** A resolvable pointer that does not say what the claim says is `wrong_context`, not `verified`.
4. **Tally and decide severity.** Compute broken / wrong-context / verified counts per Role.
5. **Write and publish the report.** Per-Role counts plus a short list of the highest-severity broken pointers; open one flat flag file per hard flag and publish via `mos_publish_to_shared`.
6. **Announce on EACN.** Short `eacn3_send_message` to each affected Role pointing at the flag files. Gru is told only when counts exceed a clear threshold or a Role has repeated offenses.

Every report and flag is marked `[evidence: <pointer>]` so Ethics eats its own dog food.

## Pitfalls

- Treating a resolvable URL as proof without checking content (overlaps with citation audit; defer when the pointer is a citation).
- Trying to verify every pointer in a large window. Sample, do not exhaustively scan; coverage proportional to claim density.
- Auditing your own Ethics artifacts without a subagent.
- Accepting an EACN event id as verified just because `eacn3_get_task` returns success; the content must also match the claim.
