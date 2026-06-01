---
slug: run-review-round
summary: Execute one formal review round as Area Chair / journal Editor — 3-5 independent reviewer reports (fanned out as concurrent foreground Task subagents) before any history, independent revision-delta pass, meta-review packet, EACN publish.
layer: composite
tools:
version: 3
status: active
supersedes:
references: simulate-reviewer-instance, revision-delta, finalize-review-packet, aspect-review
provenance: human
---

# Skill — Run Review Round

One complete formal review round; the orchestration skeleton for the 3-Pass progressive disclosure workflow used by `mos_review_run`.

## When to invoke

- `mos_review_run` has launched you with a submission package and round number.
- Previous-round summary path is or is not provided in the initial prompt (controls Pass B / C).

If the submission package is missing material the review depends on, raise it as a weakness or required revision in the consolidated packet — you do not have an EACN identity to ask for it.

## Structure

The round writes to `branches/main/reviews/round-<n>/` with `aspect-notes/` inside. Three mutually isolated passes:

- **Pass A** — 3–5 independent reviewer instances see current submission only. No prior summaries, prior reviews, rebuttals, changelogs, or orchestrator paraphrases.
- **Pass B / C** — one dedicated revision-delta subagent reads the previous rolling summary first, then current revision materials. Does not see current-round reviewer reports.
- **Meta-review** — the orchestrator consolidates; writes the packet and rolling summary.

Reviewer count starts at 3; grow to 4 or 5 when submission is complex, when reviewer decisions or major weaknesses materially disagree, or when reviewer 3 surfaces substantial new issues. Stop when the marginal reviewer is largely redundant.

## Concurrency — finish the round inside one wall

You run as a single `claude --print` process under one wall-clock cap (`review_timeout_seconds`, default 1 h). You **must** parallelize to finish:

- Spawn each reviewer instance's aspect subagents as **concurrent foreground `Task` calls** — issue several `Task` calls in one turn so they run in parallel, then read their notes when they return. Run the first 3 reviewers in parallel rather than strictly one-fully-finished-before-the-next.
- **Never use `run_in_background` or the `Workflow` tool.** This is a `--print` turn; a backgrounded `Task` or a `Workflow` is abandoned when the turn ends and its output is lost. `Workflow` is intentionally not in your allowed-tools.
- Delegate volume reading — long-PDF scans, code tracing, citation cross-checks — to a dedicated read-only `Task` subagent from inside aspect subagents.

## Procedure

1. **Read the initial prompt.** Confirm submission directory, round number, and whether a prior summary path was provided.
2. **Create the round directory.** `branches/main/reviews/round-<n>/aspect-notes/`.
3. **Run Pass A first.** Spawn reviewer instances per `simulate-reviewer-instance`, their aspect subagents fanned out as concurrent foreground `Task` calls (see Concurrency above). Pass A sees only the current submission package.
4. **Grow from 3.** Convene the first 3 reviewers concurrently; once their reports land, decide on reviewer 4 / 5 per the structure criteria. Stop when the latest reviewer is largely redundant with the others.
5. **Write `fresh.md`.** Concatenate `reviewer-1.md` through the final generated reviewer report. No summary, no reconciliation.
6. **Run Pass B / C only for revisions.** If a prior summary path was provided, spawn one `revision-delta` subagent. Otherwise write `revision_delta.md` containing only `skipped: no prior summary`.
7. **Write the meta-review packet** using `templates/consolidated.md`: notification, AC / Editor meta-review, exact `## Decision`, the Epistemic Rigor Assessment (D1–D6) section, revision-delta highlights (if any), every individual reviewer report.
8. **Consolidate the rigor scores.** Aggregate every reviewer instance's "Epistemic Rigor Summary (D1–D6)" table into the consolidated "Epistemic Rigor Assessment (D1–D6)" section: per-dimension mean across instances (1 decimal), the range when instances disagree, and the top strength / weakness per dimension. Gather every D3 over-claim flag into the prominent over-claim block with its evidence pointer. A dimension mean of 1–2, or any unresolved over-claim flag, is a critical / major finding the meta-review must foreground. Keep this section above and independent of `## Decision` — the scores inform the decision narrative but never compute the label.
9. **Write the rolling summary** using `templates/summary.md`. Compressed and safe for the next round's Pass B / C, including the six D1–D6 means and any open over-claim / scope flags so rigor history carries forward.
10. **Finalize** per `finalize-review-packet`. End the run with `consolidated.md` path and decision label on the last line.

End state: `reviewer-<i>.md` files, `fresh.md`, `revision_delta.md`, `consolidated.md`, `summaries/round-<n>.md`. Gru reads `consolidated.md` after `mos_review_run` returns and relays the result on the project's Local EACN.

The six-dimension rigor assessment is **informational, not a gate.** It is surfaced prominently in the packet, but the Accept/Reject decision stays your evidence-weighted judgment (and ultimately Gru's / the human's) — never a mechanical threshold over the dimension means. Over-claim / scope-calibration (D3) findings get the most prominent placement, per the project's anti-over-claim value.

## Pitfalls

- Treating `fresh.md` as a synthesis. It is a direct concatenation of individual reviews.
- Letting reviewer instances see prior reviews or rebuttals during Pass A.
- Counting the revision-delta subagent as one of the 3–5 reviewer instances.
- Trying to publish on EACN — you have no agent identity; Gru relays after you exit.
- Running reviewers serially (one fully done before the next starts) or backgrounding them with `run_in_background` / `Workflow` — both blow the round wall or lose output.
- Turning the D1–D6 rigor means into an auto-decision. The assessment is informational; the `## Decision` is your evidence-weighted call, never `mean < threshold ⇒ Reject`.
- Burying a D3 over-claim flag inside a per-reviewer table. Surface it in the consolidated "Prominent over-claim / scope flags" block and the rolling summary.
