---
slug: finalize-review-packet
summary: Open after consolidated.md is drafted — verify the meta-review packet is complete and well-formed, then exit with the path and decision label so mos_review_run can parse the result.
layer: logical
tools:
version: 3
status: active
supersedes: publish-review-result
references: run-review-round
provenance: human
---

# Skill — Finalize Review Packet

One self-contained markdown packet the project team can act on: notification, meta-review, decision, required revisions, revision-delta highlights, all individual reviewer reports. You assemble and verify it; Gru's `mos_review_run` parses the decision and relays the result on EACN.

## When to invoke

Called by `run-review-round` after `consolidated.md` is drafted. May also be invoked directly when an existing consolidated packet needs verification before being relayed (e.g. before re-pinging Writer).

You do not publish on EACN. You have no EACN tools. The orchestrator process is launched synchronously by `mos_review_run`; when you exit, Gru reads `consolidated.md`, extracts the `## Decision` line, and posts the result on the project's Local EACN.

## Structure

`consolidated.md` must contain: notification, Area Chair / Editor meta-review, exact `## Decision` on its own line, required revisions or camera-ready instructions, revision-delta highlights when applicable, all generated reviewer reports inlined. Decision routes Gru's next action:

| Decision | Gru relay action |
|---|---|
| `Strong Accept` / `Accept` | Notify Writer; suggest camera-ready cleanup |
| `Weak Accept` / `Borderline` | Notify Writer with revision asks; route evidence/code/experiment follow-ups to Expert / Coder / Experimenter |
| `Weak Reject` / `Reject` / `Strong Reject` | Notify Writer with substantive revision requirements |

## Procedure

1. Verify `artifacts/reviews/round-<n>/consolidated.md` contains: notification, AC / Editor meta-review, exact `## Decision <label>` on its own line (one of the seven), required revisions or camera-ready instructions, revision-delta highlights when applicable, every generated `reviewer-<i>.md` inlined in full.
2. Verify the rolling summary `artifacts/reviews/summaries/round-<n>.md` exists and contains unresolved issues, newly raised issues, resolved-since-last-round items, long-standing unanswered questions, and the final decision — without raw quotations or notification prose.
3. End your last assistant turn with the absolute path to `consolidated.md` and the final decision label on its own line. `mos_review_run` parses both.

## Pitfalls

- Producing only the decision label without inlining the individual reviews — downstream readers expect one self-contained packet.
- Splitting the meta-review and reviewer reports across multiple files instead of one consolidated.md.
- Attempting to call EACN tools to publish the result. You have no EACN agent identity; Gru relays after you exit.
- Forgetting to print the path / decision at the end of the run — `mos_review_run` falls back to parsing `consolidated.md`, but the explicit final line aids logging.
