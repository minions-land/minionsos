# MetaHarness — Skill Library Verdict (2026-05-13)

Five Sonnet sub-agents independently graded all 60 skill files on five dimensions (summary clarity, trigger coverage, procedure executability, pitfall value, structure fit), each 1–5. I read the five batch reports and aggregate them here as the meta layer.

Per-batch reports live under `minions/roles/common/_evals/`.

## Headline numbers

- **Files graded:** 60
- **KEEP:** 49 (82 %)
- **TUNE:** 9 (15 %)
- **MERGE:** 2 (3 %) — `experimenter/execution-guide` + the three `karpathy-coding-guidelines` copies
- **REWRITE / DROP:** 0

The library is fundamentally sound. The SSL four-section discipline reaches the agent without translation losses. No skill scored below 2.8 mean. No skill is judged misleading or actively harmful.

## Score distribution by batch

| Batch | Files | Mean of means | Highest | Lowest |
|---|---|---|---|---|
| common (EACN3 manual) | 14 | 4.49 | eacn3-state-machines (4.8) | eacn3-economy (3.8) |
| coder | 10 | 4.50 | bounded-repair-loop / silent-failure-audit (4.8) | karpathy-coding-guidelines (4.0) |
| writer | 13 | 4.43 | citation-audit (5.0) | imported-paper-skill-catalog (2.8) |
| experimenter + ethics | 10 | 4.52 | citation-authenticity-audit (5.0) | karpathy-coding-guidelines (3.6) |
| reviewer + gru + expert + noter | 13 | 4.40 | role-session-diff-timeline (5.0) | simulate-reviewer-instance (3.8) |

Three skills hit the perfect 5.0: `citation-audit`, `citation-authenticity-audit`, `role-session-diff-timeline`. They share three traits — concrete classification scheme, exact output paths, self-application rule — which the meta layer flags as the **house style** to enforce on weaker skills.

## Cross-cutting findings (the meta layer's verdict)

The five batches converge on five systemic issues. Listed in priority order — top of the list = highest leverage to fix.

### 1. Summary lines describe contents instead of triggers (13 of 14 common skills, ~6 of 13 writer skills, all reviewer sub-skills)

The frontmatter `summary` is the *only* signal a Role gets at wake-up before deciding to open the file. Today most summaries read as "what this file is about" instead of "open when X, outcome Y". Highest-leverage single fix in the library.

**Affected (~25 files).** Concentrated in `common/eacn3-*`, `writer/end-to-end-paper-workflow`, all reviewer sub-skills, all gru skills, both expert skills.

**Action.** Mechanical rewrite of `summary:` field only, no body changes. Pattern: `<trigger condition>; <outcome / what you get>`.

### 2. Vague trigger thresholds — "non-trivial", "important", "on idle", "behavioral impact", "suspected" (16 files across 4 batches)

This is the single most-quoted batch-level observation. A fresh Role cannot match its current situation against an undefined threshold. The strongest skills (`bounded-repair-loop` 4.8, `simplify-changes` 4.6 with its 20-line rule, `citation-authenticity-audit` 5.0 with 20-30 % sampling) all share concrete numeric or named conditions.

**Affected.** Most coder skills, `archive-execution`, `evidence-pointer-sweep`, `track-run`, `interactive-figure-prototype`, `role-skill-design`, both `karpathy-coding-guidelines` copies, several reviewer sub-skills.

**Action.** Replace each vague phrase with one concrete heuristic. Two batches independently nominated `bounded-repair-loop` and `citation-authenticity-audit` as the templates.

### 3. The three `karpathy-coding-guidelines` copies are the worst-grading skills in the library and need restructuring

Both batch reports that touched it (coder, experimenter, gru/reviewer-side) scored it lowest in their batch. Three concrete defects:

- **Slug is a proper noun.** "Karpathy" means nothing to a fresh agent who does not know the provenance. Rename to `coding-discipline`.
- **Structure section absent.** The four guidelines live inline under `## Procedure` with `### 1.`-style sub-headers, breaking the SSL template. Two batch reports flagged this independently.
- **Trigger is "always".** "Open whenever Coder, Experimenter, or Gru is about to produce non-trivial code" is a background rule, not a situational skill. Compounds issue #2.

Plus `experimenter/execution-guide` shares ~70 % of the body. Both batch4 reports recommend MERGE.

**Action.** Rename to `coding-discipline`. Rewrite to four-section template. Fold `experimenter/execution-guide`'s unique content (Experimenter / subagent dispatch split) in as a `## Experimenter application` subsection. Three role copies stay synced via the existing copy mechanism.

### 4. MinionsOS-specific guidance is buried mid-paragraph in 3 EACN3 cluster skills

`eacn3-bootstrap`, `eacn3-agent-lifecycle`, `eacn3-reputation` all contain correct guidance like "in MinionsOS the host pre-registers the agent — only `eacn3_get_agent` is typically needed", but it appears mid-paragraph instead of leading the `## When to invoke` section. A MinionsOS Role opening the file pays full body cost before learning the file is mostly irrelevant to it.

`eacn-network-collaboration` and `eacn3-event-loop` already do this correctly and set the standard.

**Action.** Reorder `## When to invoke` in the three offending files to lead with the MinionsOS case.

### 5. Caller-driven triggers in 3 reviewer sub-skills + 1 writer reference card

`aspect-review`, `simulate-reviewer-instance`, `publish-review-result` open with "Called by `<parent>`". Correct for orchestrated workflows but offers no self-invocation rule when a Role wants to use the skill outside the parent flow. `writer/paper-work-boundaries` has the same shape — its trigger reads as a usage instruction not a decision condition.

**Action.** Add one self-trigger line to each. For `paper-work-boundaries`, also add a short decision rule for cross-slot work (e.g. delegating to two paper-* subagents whose outputs need to be composed).

## Lower-priority observations (not blocking; useful for polish)

- **One factual error.** `coder/static-type-check` recommends Pyright; the project actually uses `uv run ty check minions` per `CLAUDE.md`. Single-line fix.
- **Two undefined paths.** `archive-execution` references `branches/experimenter/experiments/notes/` which appears nowhere else in docs. `triage-request` does not name the canonical location of `experiment_targets.yaml`. One-line fixes.
- **Two `[derived: ...] root §9` references** in expert skills (`dialectics`, `first-principles`) point at a SYSTEM.md section a fresh agent cannot resolve. Replace with path or quote.
- **Pitfall platitudes** in ~6 files (e.g. `change-review`'s "Reporting speculative issues without file/line evidence" duplicates step 6). Pattern: pitfall restates the procedure's own correct behavior negatively, which adds no new failure-mode information. Replace with concrete bug patterns.
- **Coverage gap (writer):** no skill covers the camera-ready *manuscript revision* cycle between rebuttal acceptance and final bundle. `prepare-rebuttal` ends at the response; `package-submission` starts at the bundle.
- **Coverage gap (common):** no skill covers EACN3 non-400 error recovery (network timeout, 503, plugin crash mid-task). `eacn3-bootstrap` touches the lost-endpoint case but a Role hitting a tool error mid-task has no retry/reconnect/escalate guidance.

## Recommended next actions, in priority order

1. **Mechanical pass: rewrite `summary` fields** on the ~25 files where summaries describe contents instead of triggers. Pure frontmatter edit, no body changes. ~30 min of work, biggest UX gain in the library.
2. **Replace vague trigger thresholds** in 16 files with concrete heuristics. ~1 h of work.
3. **Rebuild `coding-discipline`** (renamed from `karpathy-coding-guidelines`), merge `execution-guide` into it, sync three role copies. ~30 min of work; resolves the lowest-graded skills in two batches.
4. **Reorder `## When to invoke`** in `eacn3-bootstrap`, `eacn3-agent-lifecycle`, `eacn3-reputation` to lead with the MinionsOS case. ~10 min of work.
5. **Add self-triggers** to caller-driven reviewer sub-skills and `paper-work-boundaries`. ~15 min of work.
6. **Fix one factual error** (Pyright → `uv run ty check minions` in `coder/static-type-check`). ~2 min of work.

Items 7+ (path corrections, root §9 references, pitfall platitudes, coverage gaps) are polish; defer until items 1–6 are done.

## What this MetaHarness exercise actually proved

The harness was designed to answer two questions: *do the skills import correctly* (yes — see `SKILL_IMPORT_CHECK` from earlier) and *are the skills good*. The five Sonnet evaluators were briefed identically and graded independently; their batch-level observations converge on the same five systemic issues without coordination. That convergence is the strongest evidence the issues are real and not artifacts of one evaluator's preferences.

The library does **not** need REWRITE or DROP at any file. The improvements above are tuning, not replacement. The SSL four-section template is doing its job — every batch-level observation is a finding *within* the template, not against it.

If the next round wants a SkillOS-style learned curator, this MetaHarness output is a clean baseline for measuring whether learned edits move the per-dimension scores.
