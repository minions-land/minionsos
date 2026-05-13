# Batch: reviewer + gru + expert + noter

## Per-skill grades

| slug | summary | trigger | procedure | pitfalls | structure | mean | verdict |
|---|---|---|---|---|---|---|---|
| aspect-review | 4 | 4 | 4 | 4 | 4 | 4.0 | KEEP |
| code-validity-review | 5 | 4 | 5 | 5 | 5 | 4.8 | KEEP |
| publish-review-result | 5 | 4 | 4 | 3 | 4 | 4.0 | KEEP |
| revision-delta | 5 | 5 | 5 | 4 | 5 | 4.8 | KEEP |
| run-review-round | 5 | 4 | 5 | 4 | 5 | 4.6 | KEEP |
| simulate-reviewer-instance | 4 | 3 | 4 | 4 | 4 | 3.8 | TUNE |
| feature-intake | 5 | 4 | 4 | 4 | 4 | 4.2 | KEEP |
| karpathy-coding-guidelines | 4 | 3 | 5 | 5 | 3 | 4.0 | TUNE |
| project-automation-audit | 5 | 4 | 4 | 4 | 4 | 4.2 | KEEP |
| role-skill-design | 5 | 4 | 5 | 4 | 4 | 4.4 | KEEP |
| dialectics | 5 | 5 | 5 | 4 | 5 | 4.8 | KEEP |
| first-principles | 5 | 5 | 5 | 4 | 5 | 4.8 | KEEP |
| role-session-diff-timeline | 5 | 5 | 5 | 5 | 5 | 5.0 | KEEP |

## Per-skill notes

### aspect-review
- **Verdict:** KEEP
- **Strengths:** Aspect menu table is concrete and actionable; EACN-invisible boundary is stated clearly.
- **Issues:** "Called by `simulate-reviewer-instance` when spawning an aspect subagent" — trigger is entirely caller-driven with no self-invocation condition; a fresh agent cannot decide independently when to open this skill.
- **Recommended action:** Add one self-trigger line for when Reviewer main is directly asked to inspect a single narrow aspect outside the full round workflow.

### code-validity-review
- **Verdict:** KEEP
- **Strengths:** Validity-risk checklist (data leakage, seed contamination, cherry-picking, etc.) is the strongest concrete pitfall list in the batch; write-boundary rule is explicit.
- **Issues:** "Reviewer is read-only on `branches/**`" appears in Structure but not reinforced in Pitfalls — the pitfall about "Suggesting fixes in any role's branch" is good but slightly redundant with the Structure statement; could be tightened.
- **Recommended action:** Minor — merge the boundary statement into the pitfall to avoid repetition.

### publish-review-result
- **Verdict:** KEEP
- **Strengths:** Decision routing table is immediately actionable; "one self-contained markdown packet" framing is clear.
- **Issues:** Pitfalls section has only 3 entries and the third — "Asking Gru to interpret the decision before Reviewer has published the review packet" — is a sequencing concern that is not obviously a failure mode a fresh agent would anticipate. The "too large for EACN message body" fallback in Procedure step 3 is mentioned but no size heuristic is given.
- **Recommended action:** Add a pitfall for the size-fallback case (e.g., "Sending only the artifact pointer without a concise notification when the packet is large").

### revision-delta
- **Verdict:** KEEP
- **Strengths:** Pass B / Pass C isolation is precisely specified; the placeholder-for-missing-file edge case is handled explicitly.
- **Issues:** "Treating author rebuttal claims as true without checking the current submission materials" is a good pitfall but could name the failure mode more sharply — e.g., "accepting rebuttal prose as evidence of a fix without verifying the submission itself changed."
- **Recommended action:** Sharpen the rebuttal pitfall wording; otherwise no changes needed.

### run-review-round
- **Verdict:** KEEP
- **Strengths:** End-state artifact list is exhaustive and traceable; reviewer-count growth criteria are concrete (disagreement, substantial new issues, redundancy).
- **Issues:** "Missing target → ask through Local EACN instead of reviewing work-in-progress" is a good guard but buried in the trigger section with no corresponding pitfall. Step 4 ("Grow from 3") references "structure criteria" without a back-pointer to where those criteria live in the same file — a fresh agent has to re-read Structure to find them.
- **Recommended action:** Add a pitfall for "Starting Pass A without confirming the submission package is present" and add an inline reference in step 4 to the Structure section's growth criteria.

### simulate-reviewer-instance
- **Verdict:** TUNE
- **Strengths:** Composite reviewer model (aspect subagents + stance mix) is well-specified; output artifact paths are concrete.
- **Issues:** Trigger is "Called by `run-review-round` during Pass A" — entirely caller-driven, no self-invocation condition. "Different stances within the same reviewer instance wherever possible — uniform stance collapses the dynamic mix" is stated in Structure but the Procedure step 3 says only "Assign different stances to aspect subagents within this reviewer instance where possible" — the consequence of uniform stance (convergence risk) is not named in Pitfalls. "Drop only aspects genuinely irrelevant to this submission" lacks a decision rule for what counts as irrelevant.
- **Recommended action:** Add a self-trigger condition; add a pitfall naming the convergence risk from uniform stance; add a one-line heuristic for dropping aspects.

### feature-intake
- **Verdict:** KEEP
- **Strengths:** "Acceptance criteria prefer observable checks" with a concrete list (command output, file path, EACN artifact, dashboard behavior) is immediately usable.
- **Issues:** "Asking broad preference questions when the repo already implies the answer" is a good pitfall but "broad preference questions" is slightly vague — a concrete example (e.g., "asking which language to use when the repo is already Python") would sharpen it.
- **Recommended action:** Add one concrete example to the first pitfall.

### karpathy-coding-guidelines
- **Verdict:** TUNE
- **Strengths:** Procedure is the most detailed in the batch — each guideline has sub-bullets and a self-test; pitfalls are sharp and non-obvious (e.g., "Removing pre-existing dead code under the banner of Surgical Changes").
- **Issues:** Structure section is a four-item list, not the standard SSL four H2 sections — the skill uses `### 1.` sub-headers inside `## Procedure` rather than a separate `## Structure` section, making it structurally non-conformant with the template. Trigger says "Open whenever Coder, Experimenter, or Gru is about to produce non-trivial code" — "non-trivial" is undefined and the skip condition ("trivial edits") is equally vague. The skill is also notably longer than the ≤60-line guideline from CLAUDE.md (95 lines).
- **Recommended action:** Extract the four-guideline list into a proper `## Structure` section; define "non-trivial" with one concrete threshold (e.g., "more than one function or more than ~20 lines changed"); trim to ≤60 lines by condensing sub-bullets.

### project-automation-audit
- **Verdict:** KEEP
- **Strengths:** "Advisory by default" framing prevents scope creep; category cap (two recommendations per category) is a concrete constraint.
- **Issues:** "Multiple roles repeatedly hit the same manual coordination or validation step" is a valid trigger but requires cross-role observation that Gru may not always have — no guidance on how to detect this. Step 6 "Route follow-up. Use `feature-intake` for accepted work" is correct but the condition for "accepted" is not defined (accepted by whom, via what signal).
- **Recommended action:** Add a note on how Gru detects repeated friction (EACN history, role logs); clarify "accepted" in step 6 as "author explicitly approves an `install now` recommendation."

### role-skill-design
- **Verdict:** KEEP
- **Strengths:** Template reference (`minions/roles/common/_skill_template.md`) and discovery mechanism are named precisely; "subagents do not automatically inherit role skills" pitfall is non-obvious and valuable.
- **Issues:** "A role repeatedly makes the same coordination, evidence, or boundary mistake" is a valid trigger but "repeatedly" is undefined — no threshold given. Step 7 "Update role prompt only when needed" is vague; "only when needed" is not actionable without a criterion.
- **Recommended action:** Define "repeatedly" (e.g., "same mistake observed in two or more role sessions"); sharpen step 7 with a concrete condition (e.g., "only when the role has no existing skill reference and the new skill changes a default behavior").

### dialectics
- **Verdict:** KEEP
- **Strengths:** "A genuine synthesis predicts new things" is a sharp, testable criterion; four dialectic patterns (scale, distribution, metric, short/long-term) are domain-relevant and concrete.
- **Issues:** "False-balance trap" pitfall — "Some theses are simply correct with no meaningful antithesis. Manufacturing one to look rigorous is worse than stating the thesis directly" — is the best pitfall in the batch. Minor: the `[derived: dialectical synthesis of ...]` marking instruction in step 6 references "root §9" which a fresh agent cannot resolve without knowing the root SYSTEM.md section numbering.
- **Recommended action:** Replace "root §9" with the actual convention text or a path reference (e.g., "per the evidence-first convention in `minions/roles/SYSTEM.md`").

### first-principles
- **Verdict:** KEEP
- **Strengths:** "Reserve for the ~20% of questions where framing itself is the problem" is a rare and useful scope-limiter; "Crank mode" pitfall is sharp.
- **Issues:** Step 5 `[derived: first-principles from <primitive-list>]` has the same "root §9" reference problem as dialectics. "Divergence from literature is a flag, not a license" is stated in Structure but not reinforced in Pitfalls — the "Crank mode" pitfall covers it partially but doesn't name the specific failure of rejecting accumulated evidence without new data as a distinct pattern from simply diverging.
- **Recommended action:** Fix "root §9" reference; optionally split "Crank mode" into two pitfalls: (1) rejecting literature without new data, (2) treating every question as first-principles material (currently listed separately but could be merged for clarity).

### role-session-diff-timeline
- **Verdict:** KEEP
- **Strengths:** Cursor schema is given verbatim; atomic write pattern (`.tmp` + rename) is specified; the 50-archive-per-wake cap prevents runaway processing; EACN drain prohibition is stated three times (frontmatter tools list, Structure, Pitfalls) — appropriate given the severity.
- **Issues:** No meaningful issues. This is the strongest skill in the batch on all five dimensions.
- **Recommended action:** None.

## Batch-level observations

- **"root §9" reference rot.** Both expert skills (`dialectics`, `first-principles`) reference "root §9" for the evidence-marking convention. A fresh agent cannot resolve a section number without reading the root SYSTEM.md and counting sections. Both should be updated to cite the path or quote the convention inline.

- **Caller-driven triggers dominate the reviewer sub-skills.** `aspect-review`, `simulate-reviewer-instance`, and `publish-review-result` all open with "Called by X" as their primary trigger. This is correct for composite workflows but leaves a fresh agent unable to self-invoke these skills outside the orchestrated path. At minimum, each should state whether self-invocation is ever valid.

- **Structure section is used inconsistently.** Most skills use `## Structure` as a compact pre-procedure summary (good). `karpathy-coding-guidelines` folds its structure into the procedure sub-headers, breaking the SSL template. `role-session-diff-timeline` uses Structure for the cursor schema and boundary rules — the most information-dense use in the batch and it works well.

- **Length discipline.** `karpathy-coding-guidelines` at 95 lines is the only skill that materially exceeds the ≤60-line guideline. The reviewer sub-skills (`run-review-round`, `simulate-reviewer-instance`) are at the upper edge (~54 lines) but justified by their composite orchestration role.

- **Pitfall quality is bimodal.** The best pitfalls in the batch are concrete failure modes with named consequences (`code-validity-review`'s checklist, `dialectics`'s false-balance trap, `role-session-diff-timeline`'s drain warning). The weakest are vague behavioral advice: `feature-intake`'s "broad preference questions," `project-automation-audit`'s "recommending generic tooling without evidence." The gap is whether the pitfall names a specific wrong action and its consequence, or just restates the correct behavior negatively.

- **No redundancy or merge candidates** across the 13 skills. The reviewer sub-skills form a clean hierarchy (`run-review-round` → `simulate-reviewer-instance` → `aspect-review`; `run-review-round` → `revision-delta` → `publish-review-result`) with no content overlap. The two expert skills (`dialectics`, `first-principles`) are complementary and cross-reference each other correctly.
