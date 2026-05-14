# MinionsOS Skill Library — Two-Axis Audit

Audit date: 2026-05-14. Scope: 57 skills under `minions/roles/{role}/skills/` (excluding `coding-methodology`, which was already evaluated and fixed in earlier rounds). The EACN3 dependency folder was not touched. The audit answered two orthogonal questions per skill:

- **Recall (Stage A / SSL).** Given only frontmatter summaries, would the right skill be selected for a probe scenario that should trigger it?
- **Coherence (Stage B).** Reading the body, does the skill read as one coherent piece, or as a stitched-together monster (缝合怪) where multiple disparate concepts are forced into one file?

## Headline

| Axis | Pass | Fail | Pass rate |
|---|---|---|---|
| Recall@3 | 57 | 0 | 100% |
| Recall@1 | 57 | 0 | 100% |
| Coherence (COHERENT) | 53 | 4 NEEDS POLISH (0 REWRITE, 0 STITCHED) | 93% |

**No recall failures. No skill is a 缝合怪.** The library is in usable shape. Four skills need polish; one of those polishes (`allocate-resources` ↔ `dispatch-runner` boundary) is a real chain defect, the other three are wording / partition fixes.

## Two-axis matrix

```
                       Coherence: COHERENT     Coherence: NEEDS POLISH
Recall: HEALTHY        53 skills (kept)        4 skills (polish below)
Recall: FAILED         —                       —
```

## The four NEEDS POLISH skills

### 1. experimenter/allocate-resources ↔ experimenter/dispatch-runner — chain defect (real)

**Symptom.** Both skills call `exp_queue_submit`. A Role following `allocate-resources` end-to-end has already submitted; `dispatch-runner` step 1 then either no-ops or double-submits. The "When to invoke" of `dispatch-runner` says "after `allocate-resources` produces queue-ready units" — only consistent if `allocate-resources` does not submit. Today it does.

**Recommended fix (option 1, preferred).**
- Make `allocate-resources` purely a planner: output queue-ready unit specs, drop `exp_queue_submit` from its `tools` and procedure step 3.
- Keep the `exp_queue_submit` call, batch-id persistence, EACN handoff, and subagent delegation in `dispatch-runner`.

**Alternative (option 2).** Merge them into one `submit-resources` skill. Loses some abstraction but the residual content of `dispatch-runner` is mostly bookkeeping.

Recommendation: option 1.

### 2. coder/feature-implementation — counting and duplication polish

**Symptom.** Structure block says "Five phases" then enumerates seven items in the same sentence; Procedure delivers seven numbered steps. The "abstraction is justified only when..." rule is stated in Structure and re-stated almost verbatim in Procedure step 3.

**Fix.** Either re-label as "Seven phases" matching the Procedure, or collapse Procedure to five real phases by folding "simplify" + "handoff" into "verify" / final reporting. Drop the duplicated abstraction sentence from Structure; let it live only in step 3.

### 3. common/eacn3-event-loop — orthogonal surface bundled in

**Symptom.** Skill bundles the three queue-drain tools (`get_events` / `await_events` / `next`) plus the event taxonomy (one clean cluster) with `eacn3_reverse_control_status`, which inspects the sampling / notifications subsystem (a different surface — agents call it when debugging "why is sampling not firing?", not "drain my queue").

**Fix.** Move `eacn3_reverse_control_status` into a small `eacn3-reverse-control` skill, or fold it into `eacn3-agent-lifecycle` (where the `reverse_control` registration option already lives). If splitting is too heavy, at minimum re-frame the section header to acknowledge the orthogonal surface.

### 4. writer/paper-search-tools — tool reference + discipline essay duct-taped

**Symptom.** Frontmatter sells this as a tool reference. Body delivers tool list + fallbacks (good) but procedure leans into general literature-search discipline ("Search with a claim in mind", "Separate paper classes", "Never fabricate BibTeX") that is broader than the listed tools.

**Fix (two paths).**
- **A.** Keep slug, trim procedure to tool-usage tactics (input shaping, pagination, when to read vs skim, when to fall back to WebSearch). Move general search discipline into `imported-paper-skill-catalog`'s notes or a dedicated `literature-search-discipline.md`.
- **B.** Rename to `paper-literature-search`, keep both halves, declare the dual role explicitly in the summary.

Recommendation: A — keeps the tool-reference focus and pushes broader discipline into a properly-typed home.

### Cross-skill (not a single-skill polish, but flagged)

**reviewer/code-validity-review vs reviewer/aspect-review (`experiments` + `reproducibility` aspects).** ~70% scope overlap. Both cover seeds, leakage, baselines, metrics, code-traceable evidence. A Reviewer main can't tell from the two skill files alone whether to invoke `aspect-review` with `experiments` aspect or call `code-validity-review` directly. **Fix:** reposition `code-validity-review` as the deep-trace zoom of `experiments` + `reproducibility` (with an explicit one-line scope note), or fold it into `aspect-review` as a callable mode. Pick one.

## Minor items (one-pass cleanup, no rewrites needed)

- **Broken reference.** `common/eacn3-error-recovery` frontmatter `references:` lists `eacn-network-collaboration` (missing the `3`). No skill by that name exists. Likely intended `eacn3-network-overview`. Trivial fix.
- **Citation-audit lane note.** `writer/citation-audit` and `ethics/citation-authenticity-audit` both audit existence + metadata + context; the de-facto lanes (writer = full pre-submission sweep; ethics = sampled watchdog escalating via EACN) work, but neither file references the other. Add one-line cross-pointer in each "When to invoke" so future editors don't collapse or duplicate them.
- **Bid-FSM mini-diagram label drift.** `eacn3-network-overview` uses informal `accepted` / `submitted`; `eacn3-state-machines` uses canonical `rejected / waiting_execution / executing / waiting_subtasks / submitted / pending_confirmation`; `eacn3-task-executor` ends its slice at `awaiting_retrieval` (a Task-FSM state). None contradict behaviour; cosmetic.

## What this audit clears (do nothing)

The remaining **53 skills** are coherent, recall-healthy, and partition cleanly across their clusters. Notable cluster strengths:

- **Coder cluster (7 skills).** No 缝合怪. The three review-flavored skills (`static-type-check`, `type-design-review`, `test-coverage-review`) have distinct triggers and artifacts; the boundary-discipline repetition is feature, not bug.
- **EACN3 cluster (15 skills, common/eacn3-* + 2 glue).** Progressive disclosure design holds: `eacn3-network-overview` actually routes, `eacn3-state-machines` is the FSM authority, sister skills cite by name without re-explaining. `delegate-heavy-task` and `eacn-network-collaboration` stay decision/glue skills, not tool tutorials.
- **Reviewer cluster (6 skills).** Pass A isolation enforced at three layered places (run-review-round, simulate-reviewer-instance, aspect-review pitfalls). Sub-skill partition is clean except for the code-validity-review overlap noted above.
- **Writer cluster (14 skills).** `end-to-end-paper-workflow` orchestrates without re-implementing — the right pattern for composite skills. Figure trio (academic-plotting / figure-spec / interactive-figure-prototype) and LaTeX chain (make-latex-model → paper-compile → package-submission) have clean lanes.
- **Expert / Gru / Noter / Ethics / Experimenter (12 skills)**. All single-purpose. `noter/role-session-diff-timeline` is deliberately just the diff/timeline step (a stitched Noter skill would also do cadence summaries + EACN reporting); ethics skills tie taxonomy to procedure tightly.

## Method caveat

The Stage A recall test is a single-judge self-simulation — probes were written right after reading the catalog, so they inherit the catalog's vocabulary, biasing recall upward versus a blind external judge. Recall@3 = 1.00 should therefore be read as "the library is at least workable", not "the library is universally findable". The six distractor clusters surfaced by Stage A (eacn-network-collaboration vs eacn3-network-overview; ethics vs writer citation audit; build-playground vs interactive-figure-prototype; reviewer triple; experimenter pipeline phases; apply-revisions vs prepare-rebuttal) are where genuine semantic overlap exists and where a noisier real probe is most likely to flip the rank. Stage 1 (behavioural A/B) on the highest-leverage skills should track these clusters specifically.

## Action list (in order of leverage)

1. **Fix `allocate-resources` ↔ `dispatch-runner` boundary** — real chain defect. Make `allocate-resources` a pure planner, keep submit in `dispatch-runner`.
2. **Resolve `code-validity-review` ↔ `aspect-review` overlap** — cross-skill ambiguity that affects every review round. Reposition or fold.
3. **Polish `coder/feature-implementation`** — fix count mismatch and duplicated abstraction sentence.
4. **Polish `common/eacn3-event-loop`** — split out `eacn3_reverse_control_status` or fence it.
5. **Polish `writer/paper-search-tools`** — trim to tool tactics, push discipline content to a new home.
6. **One-line minor cleanups** — `eacn3-error-recovery` reference typo; cross-pointer between writer/citation-audit and ethics/citation-authenticity-audit; optionally harmonise three Bid-FSM mini-diagrams.

## Files

- `library_catalog.txt` — 57 skills, frontmatter summaries only.
- `probes.md` — one probe scenario per skill.
- `stage_a_recall_report.md` — full per-skill recall results, distractor clusters.
- `stage_b_coder.md` (7 skills)
- `stage_b_eacn3_a.md` (7 skills)
- `stage_b_eacn3_b.md` (9 skills)
- `stage_b_ethics_experimenter.md` (8 skills)
- `stage_b_expert_gru_noter_reviewer.md` (12 skills)
- `stage_b_writer.md` (14 skills)
