# Batch: experimenter + ethics

## Per-skill grades

| slug | summary | trigger | procedure | pitfalls | structure | mean | verdict |
|---|---|---|---|---|---|---|---|
| allocate-resources | 5 | 4 | 5 | 4 | 5 | 4.6 | KEEP |
| archive-execution | 4 | 4 | 4 | 4 | 5 | 4.2 | KEEP |
| collect-report | 5 | 5 | 5 | 4 | 5 | 4.8 | KEEP |
| dispatch-runner | 5 | 4 | 4 | 4 | 5 | 4.4 | KEEP |
| execution-guide | 4 | 4 | 4 | 4 | 5 | 4.2 | MERGE |
| karpathy-coding-guidelines | 3 | 3 | 5 | 4 | 3 | 3.6 | MERGE |
| track-run | 5 | 4 | 5 | 4 | 5 | 4.6 | KEEP |
| triage-request | 5 | 5 | 5 | 4 | 5 | 4.8 | KEEP |
| citation-authenticity-audit | 5 | 5 | 5 | 5 | 5 | 5.0 | KEEP |
| evidence-pointer-sweep | 5 | 4 | 5 | 5 | 5 | 4.8 | KEEP |

## Per-skill notes

### allocate-resources
- **Verdict:** KEEP
- **Strengths:** Precise unit-structure definition; the pitfall list directly counters real over-engineering instincts (2× VRAM padding, serial launches).
- **Issues:** "Batches are labels; new requests merge into the project-global pending pool automatically" — a fresh agent has no prior context for what "labels" means here; one sentence of grounding would help.
- **Recommended action:** Add a one-sentence gloss on what a "batch" is vs. a "unit" in the Structure section.

### archive-execution
- **Verdict:** KEEP
- **Strengths:** The selectivity framing ("most runs should not produce a template") is the right corrective instinct and is stated clearly.
- **Issues:** "branches/experimenter/experiments/notes/" — this path appears nowhere else in the codebase docs; a fresh agent cannot verify it exists. Also "on idle time" as a trigger is vague.
- **Recommended action:** Replace the ambiguous branch path with the canonical `artifacts/exp-templates/` only, and tighten "on idle time" to a concrete condition (e.g., "when no runs are in flight and ≥ 2 prior runs share a pattern").

### collect-report
- **Verdict:** KEEP
- **Strengths:** The 500 MB pull cap, the fact/interpretation split, and the EACN one-liner-not-full-report rule are all concrete and immediately actionable.
- **Issues:** "Format per SYSTEM.md" is repeated twice (Structure and Procedure step 3) — minor redundancy.
- **Recommended action:** Remove the duplicate reference in Structure; keep it only in Procedure step 3.

### dispatch-runner
- **Verdict:** KEEP
- **Strengths:** The "submit once, persist the batch id, exit" framing is crisp and directly counters the blocking-wait anti-pattern.
- **Issues:** "§Fire-and-poll" in the pitfalls section references a section heading that does not appear in this file — a fresh agent cannot locate it. The subagent whitelist rule (`exp_*` only) is stated in both Structure and Procedure step 4, creating redundancy.
- **Recommended action:** Replace "§Fire-and-poll" with a self-contained one-line explanation; remove the duplicate whitelist statement from Structure.

### execution-guide
- **Verdict:** MERGE
- **Strengths:** The Experimenter/subagent split rule (step 5) is the one piece of content not covered by `karpathy-coding-guidelines`.
- **Issues:** Steps 1–4 ("Think before coding", "Simplicity first", "Surgical changes", "Goal-driven steps") are a compressed restatement of `karpathy-coding-guidelines`. The phrase "A discipline for hands-on experiment work, whether you do it yourself or dispatch it to a subagent" is ambiguous — Experimenter main is not supposed to do hands-on work at all per the role boundary table. "When tempted to 'just refactor this quickly while I'm here'" is a valid trigger but reads as a Coder trigger, not an Experimenter one.
- **Recommended action:** Merge into `karpathy-coding-guidelines` as an "Experimenter application" subsection covering only the dispatch/subagent split and escalation rules; drop the duplicated four-rule summary.

### karpathy-coding-guidelines
- **Verdict:** MERGE
- **Strengths:** The procedure section is the most detailed and actionable in the batch — concrete examples, the "200 lines vs 50" test, the step-plan template.
- **Issues:** The slug "karpathy-coding-guidelines" is a proper-noun attribution that means nothing to a fresh agent who does not know the provenance. The trigger says "Coder, Experimenter, or Gru" but this file lives under `experimenter/skills/` — a fresh Experimenter agent will not know it applies to Coder. Structure section is absent (the four guidelines are listed inline in the H1 body, not under a `## Structure` heading), breaking the four-section SSL contract. "For trivial tasks, use judgment" is too weak a boundary — it will be ignored.
- **Recommended action:** Rename slug to `coding-discipline`; add a proper `## Structure` heading; tighten the trivial-task boundary to a concrete example; merge `execution-guide`'s Experimenter-specific dispatch rules into a new `## Experimenter application` subsection.

### track-run
- **Verdict:** KEEP
- **Strengths:** Cold-start recovery as step 1 is exactly right for an ephemeral agent; the failure-routing table (tracebacks → Coder, design failures → Expert) is concrete and saves decision time.
- **Issues:** "log silence past a threshold" — threshold is never defined; a fresh agent cannot act on this without guessing.
- **Recommended action:** Define a concrete default silence threshold (e.g., "no log output for > 10 min on a run expected to emit per-step logs") in the anomaly detection step.

### triage-request
- **Verdict:** KEEP
- **Strengths:** The five-verdict taxonomy (`accept`, `queue`, `defer`, `redirect`, `need_info`) with explicit downstream handoff is the clearest decision structure in the batch. The "operational gatekeeper, not scientific judge" framing is well-enforced throughout.
- **Issues:** "Cross-reference `experiment_targets.yaml`" — a fresh agent does not know where this file lives relative to the project root. Minor.
- **Recommended action:** Add the canonical path (`minions/config/experiment_targets.yaml.example` or the runtime copy) as a parenthetical.

### citation-authenticity-audit
- **Verdict:** KEEP
- **Strengths:** The four-category classification scheme (`verified`, `drift`, `wrong_context`, `fabricated`) is precise and distinguishes cases that agents routinely conflate. The sampling strategy (20–30%, weighted toward recently added and high-stakes entries) is immediately actionable. Pitfalls are the strongest in the batch — each one names a specific failure mode with a concrete corrective.
- **Issues:** No meaningful issues. The "never aggregator pages" rule could name one or two examples (ResearchGate, Semantic Scholar) for a fresh agent who may not know what counts as an aggregator — but the pitfall section already names ResearchGate, so this is covered.
- **Recommended action:** None required.

### evidence-pointer-sweep
- **Verdict:** KEEP
- **Strengths:** The pointer-type resolution table is the right format for this skill — a fresh agent can work through it mechanically. "Ethics eats its own dog food" is a memorable and enforceable self-application rule.
- **Issues:** "Periodically during active research phases (e.g. once per phase or on idle)" — "on idle" is vague (same issue as `archive-execution`). "Sample, do not exhaustively scan; coverage proportional to claim density" is good advice but gives no concrete sample size, unlike `citation-authenticity-audit`'s 20–30% guidance.
- **Recommended action:** Replace "on idle" with a concrete condition; add a default sample size (e.g., "last 50 EACN messages per role, or last 10 artifacts") to match the specificity of the citation audit skill.

## Batch-level observations

- **execution-guide / karpathy-coding-guidelines overlap:** These two files share ~70% of content (the four coding rules). A fresh agent reading both gets the same guidance twice with slightly different framing. Merge is the right call; the only unique content in `execution-guide` is the Experimenter/subagent dispatch split, which should become a subsection of the merged file.

- **"on idle" vagueness pattern:** Both `archive-execution` and `evidence-pointer-sweep` use "on idle time" or "on idle" as a trigger. This is not actionable for an ephemeral agent that has no persistent sense of idle time. Both should be replaced with a concrete condition (no runs in flight, end of phase, etc.).

- **Undefined thresholds:** `track-run` references "log silence past a threshold" without defining it. `evidence-pointer-sweep` gives no sample size. `citation-authenticity-audit` sets the gold standard here with its 20–30% weighted sampling rule — the other two should match that specificity.

- **Slug naming:** `karpathy-coding-guidelines` is the only slug in the batch that uses a proper noun. It will be opaque to any agent that does not know the provenance. Rename to `coding-discipline` or `coding-guidelines`.

- **Ethics skills are the strongest pair in the batch.** Both `citation-authenticity-audit` and `evidence-pointer-sweep` have clear classification schemes, concrete output paths, and self-application rules. They set the quality bar for the experimenter skills.

- **No gaps in experimenter coverage.** The eight experimenter skills form a coherent pipeline: triage → allocate → dispatch → track → collect → archive, with execution-guide/karpathy as cross-cutting discipline. No missing step was identified.

- **Structure compliance:** All files except `karpathy-coding-guidelines` follow the four-section SSL split (When to invoke / Structure / Procedure / Pitfalls). `karpathy-coding-guidelines` embeds its structure inline under the H1 body rather than under a `## Structure` heading.
