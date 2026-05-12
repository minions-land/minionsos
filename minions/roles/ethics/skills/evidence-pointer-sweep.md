# Skill — Evidence Pointer Sweep

Confirm that the `[evidence: <pointer>]` markers on EACN messages and in artifacts actually resolve to something real: the referenced artifact path exists, the commit SHA is reachable, the URL is live, the EACN event id corresponds to a real past event.

## Core move

The evidence-first EACN convention only has bite if pointers are audited. A broken or fabricated pointer is a quiet hallucination — it looks compliant, but an auditor who clicks through finds nothing. Ethics samples pointers periodically and treats broken ones as flags.

## Procedure

1. **Collect pointers in scope.** Pick a window (last N EACN messages per role, last N artifacts under a given Role's write scope, or a specific handoff you were asked to audit). Extract each `[evidence: ...]` and `[derived: ...]` marker together with its enclosing claim and source (Role, event id, file path).
2. **Classify the pointer type and resolve it.**
   - Artifact path (`artifacts/exp-<id>/report.md`, `branches/<role>/paper/...`, etc.): check the file exists in the project, commit SHA that introduced it (via `git log --follow`), and — for bundles — that the report file points at real logs/CSVs/checkpoints.
   - Commit SHA: confirm the SHA exists in the project-worktree history; check what files it touched so the claim is plausibly supported.
   - URL: HEAD-fetch it to confirm reachability. For academic URLs, confirm title and author match the claim (this overlaps with the citation-authenticity skill; defer to that skill for citation-shaped cases).
   - EACN event id: confirm via `eacn3_get_task(task_id)` or `eacn3_get_messages(agent_id)` that the referenced event or task exists and carries the claimed content.
3. **Cross-check the claim.** A resolvable pointer that does not say what the claim says is `wrong_context`, not `verified`. For example, an `exp-<id>/report.md` that reports a different metric than the EACN claim is cited for.
4. **Tally the sample and decide severity.** Compute broken / wrong-context / verified counts per Role. One broken pointer in a low-stakes discussion message is a soft nudge; a broken pointer under a camera-ready claim is a hard flag.
5. **Write the report.** `artifacts/ethics/reports/evidence-sweep-<ts>.md` with per-Role counts and a short list of the highest-severity broken pointers. Open a flag file under `artifacts/ethics/flags/open/` for each hard flag.
6. **Announce on EACN.** Short `mos_send_message` to each affected Role pointing at the flag files. Gru only hears about the sweep if the counts exceed a clear threshold or a Role has repeated offenses.

## When to invoke

- Periodically during active research phases (e.g. once per phase or on idle).
- Before Review rounds, so Reviewer does not inherit silently broken pointers.
- After a round of heavy refactoring or experiment regeneration, where artifact paths may have moved.
- On request from Gru or the author, especially before a high-stakes decision.

## Pitfalls

- Treating a resolvable URL as proof without checking content (overlaps with citation audit; delegate to that skill when the pointer is a citation).
- Trying to verify every pointer in a large window. Sample, don't exhaustively scan; keep per-Role coverage proportional to claim density.
- Auditing your own Ethics artifacts. Use a subagent for self-review if needed.
- Accepting an EACN event id as verified just because `eacn3_get_task` returns success; the event content must also match the claim.

## Output habit

- Sweep reports stay under `artifacts/ethics/reports/`.
- Each flag file cites the source event/file and the resolution status of the pointer.
- Every report and flag is marked with `[evidence: <pointer>]` per the Evidence-first EACN communication convention so Ethics eats its own dog food.
