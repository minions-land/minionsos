# Stage B Coherence — ethics + experimenter (8 skills)

Audit date: 2026-05-14. Read-only review of 8 skill files; no edits made.

## Bucket summary

| Skill | Bucket | Confidence |
|---|---|---|
| ethics/citation-authenticity-audit | COHERENT | high |
| ethics/evidence-pointer-sweep | COHERENT | high |
| experimenter/triage-request | COHERENT | high |
| experimenter/allocate-resources | NEEDS POLISH | high |
| experimenter/dispatch-runner | NEEDS POLISH | high |
| experimenter/track-run | COHERENT | high |
| experimenter/collect-report | COHERENT | high |
| experimenter/archive-execution | COHERENT | high |

Counts: 6 COHERENT, 2 NEEDS POLISH, 0 NEEDS REWRITE, 0 STITCHED-TOGETHER.

The two NEEDS POLISH skills are a single overlap zone, not two independent flaws — `allocate-resources` and `dispatch-runner` both invoke `exp_queue_submit`, so the boundary between them is muddled even though each file individually reads cleanly.

## Per-skill verdicts

### ethics/citation-authenticity-audit — COHERENT
Single load-bearing trigger ("Hallucinated citations are the single highest-signal Ethics failure mode"). Four-class taxonomy (`verified` / `drift` / `wrong_context` / `fabricated`) is the spine of the skill, and every procedure step + pitfall ties back to it. Output habit is concrete (`artifacts/ethics/flags/open/<slug>.md` plus a batch report).

Evidence:
- "Sample, verify, flag." — body is exactly that.
- Pitfall "Flagging `drift` as `fabricated`" — directly maps to the taxonomy the procedure produces.

No action needed.

### ethics/evidence-pointer-sweep — COHERENT
Frontmatter promise ("Audit `[evidence: ...]` / `[derived: ...]` markers") matches body. Pointer-kind table is load-bearing and reused in step 2. Cross-reference to `citation-authenticity-audit` is explicit and correct ("defer citation-shaped cases").

Evidence:
- "Treat broken / mismatched pointers as quiet hallucinations." — single thesis.
- Pitfall "Treating a resolvable URL as proof without checking content" — derives directly from the wrong_context vs verified split.

Light note: pointer-kind table re-states some content already implicit in step 2; not a coherence problem, just slight redundancy.

### experimenter/triage-request — COHERENT
Pure-decision discipline. Verdicts (`accept` / `queue` / `defer` / `redirect` / `need_info`) are the spine; the procedure produces exactly one of those. The pitfall "Triaging into execution in one step" explicitly polices the boundary against `allocate-resources` — good chain hygiene.

Evidence:
- "You are the operational gatekeeper — not the scientific judge."
- "Keep triage a pure decision; resource planning is separate."

No action needed.

### experimenter/allocate-resources — NEEDS POLISH
Body is internally coherent (sizing → submit → reconcile → record) but step 3 explicitly calls `exp_queue_submit`, which is also `dispatch-runner`'s entire reason for existing. The frontmatter even lists `exp_queue_submit` as a tool. So at the cluster level the boundary leaks.

Evidence:
- Step 3: "**Submit, don't hand-pack.** Call `exp_queue_submit` with all units."
- Frontmatter tools include `exp_queue_submit, exp_queue_reconcile, exp_gpu_pool_set, exp_put`.

Recommendation: pick one of the two clean cuts:
1. Make `allocate-resources` purely planning (output: queue-ready unit specs); push the actual `exp_queue_submit` call into `dispatch-runner`. Drop `exp_queue_submit` from this skill's `tools` list.
2. Or, fold `dispatch-runner` into `allocate-resources` and rename to `submit-resources`, since the residual content of `dispatch-runner` (record batch id, broadcast handoff, subagent delegation) is mostly bookkeeping around the same submit call.

I'd lean toward option 1: keeps `allocate-resources` as a pure planner, leaves the queue side-effect in one place.

### experimenter/dispatch-runner — NEEDS POLISH
Reads cleanly on its own (submit, persist batch id, exit, optionally delegate to subagent, EACN broadcast). But its sole tool `exp_queue_submit` and its body's first procedure step duplicate `allocate-resources` step 3 verbatim in spirit. The "When to invoke" first bullet — "After `allocate-resources` produces queue-ready units" — only makes sense if `allocate-resources` did **not** submit; today's `allocate-resources` does submit, leaving `dispatch-runner` redundant.

Evidence:
- Step 1: "**Submit all units.** `exp_queue_submit(units=[...])`"
- Same `exp_queue_submit` appears as the central step in `allocate-resources` step 3.

Recommendation: see the partner recommendation under `allocate-resources`. Option 1 reshapes `dispatch-runner` into the actual submit + handoff phase; option 2 deletes this file. The unique surviving content (subagent delegation rule, EACN broadcast format) should be preserved into whichever file remains.

### experimenter/track-run — COHERENT
Single thesis ("Experimenter is ephemeral; the Python queue and detached experiments are not"). Concrete anomaly thresholds are load-bearing and reused in step 4. Failure routing (Coder / Expert / self) is operational, not philosophical. Doesn't silently take over `collect-report`'s job — step 7 writes a *tracking* note, not a result bundle.

Evidence:
- "Cold-start recovery first; cheap polling next; narrow waits only when one specific downstream action truly blocks."
- Pitfall "Polling with long `exp_wait` loops — violates fire-and-poll."

No action needed.

### experimenter/collect-report — COHERENT
Single trigger (`exp_status` terminal state). Single artifact (`artifacts/exp-{id}/report.md` + bundle). Sharp boundary against Expert ("Report, do not adjudicate — that is Expert's job"). The 500 MB pull cap is operational and concrete. Closes the run's tracking entry so `track-run` stops polling — clean handoff.

Evidence:
- "Assemble the operational record of one run so Expert, Noter, Writer, and future Experimenter invocations can consume it without re-reading logs."
- Pitfall "Dumping raw logs as the 'report.'"

No action needed.

### experimenter/archive-execution — COHERENT
Distinct from `collect-report` by timescale and scope: per-run bundles stay in `artifacts/exp-{id}/`; reusable distillations land in `artifacts/exp-templates/`. The "Decide what is reusable" step explicitly polices selectivity, which is the main risk for this kind of skill.

Evidence:
- Pitfall "Archiving everything. Most runs should not produce a template; the signal is in selectivity."
- "Per-run bundles stay in `artifacts/exp-{id}/` — do not move them." — explicit non-overlap with `collect-report`.

No action needed.

## Experimenter chain handoff analysis

Chain: triage-request → allocate-resources → dispatch-runner → track-run → collect-report → archive-execution.

- **triage-request → allocate-resources: clean.** triage emits a verdict; only `accept` flows on. The pitfall "Triaging into execution in one step" explicitly defends this boundary.
- **allocate-resources → dispatch-runner: OVERLAP (load-bearing).** Both files perform `exp_queue_submit`. Today, if a Role faithfully follows `allocate-resources` end-to-end it has already submitted to the queue, leaving `dispatch-runner`'s step 1 to either no-op or double-submit. This is the only real chain defect found.
- **dispatch-runner → track-run: clean.** `dispatch-runner` persists `{batch_id, unit_ids}`; `track-run` recovers state with `exp_queue_status(batch_id)`. Cleanly serialized through scratchpad / requester-facing note.
- **track-run → collect-report: clean.** `track-run`'s terminal-state observation is `collect-report`'s trigger. No crossover into bundle assembly. `collect-report` step 6 closes the tracking entry so `track-run` stops polling — explicit hand-back.
- **collect-report → archive-execution: clean.** `collect-report` writes `artifacts/exp-{id}/report.md`; `archive-execution` writes `artifacts/exp-templates/<slug>.md` and links back from the report. Different scopes, different files, explicit bidirectional pointer.

### Gaps

- **Mid-run priority change / re-prioritization.** No skill names this case explicitly. `track-run`'s `exp_queue_reconcile` step is the closest hook, but reconcile is described as "in case GPUs free up", not as "in case the user / Gru promotes a deferred batch." If priority bumping is a live operation, it deserves either an extra triage-request bullet ("revisited after a dependency clears" hints at it but does not cover priority changes) or a small dedicated skill. Not urgent unless it's a real workflow.
- **Cross-batch dedup at submit time.** `triage-request` mentions duplicate-of-running-job detection, but `allocate-resources` / `dispatch-runner` do not re-check before submitting. Low risk in current flow but worth a note.

### Overlaps

Only one real overlap: `allocate-resources` ↔ `dispatch-runner` over `exp_queue_submit`. Recommended fix in the per-skill verdicts above.

## Summary

The cluster reads as a coherent procedural chain, not a stitched-together monster. Both Ethics skills are tight and singly-thematic; five of the six Experimenter skills are coherent and chain cleanly. The one defect worth fixing is the `allocate-resources` ↔ `dispatch-runner` boundary, where both skills today call `exp_queue_submit`. Picking one as planner and the other as submitter (or merging them into a single `submit-resources` skill) resolves the entire issue without touching any other file.
