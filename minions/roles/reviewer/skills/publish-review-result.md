---
slug: publish-review-result
summary: Open after consolidated.md is complete (called by run-review-round) to publish the review packet via Local EACN as one self-contained markdown deliverable.
layer: logical
tools: eacn3_create_task, eacn3_send_message
version: 2
status: active
supersedes:
references: run-review-round, eacn3-mcp
provenance: human
---

# Skill — Publish Review Result

One self-contained markdown packet the project team can act on: notification, meta-review, decision, required revisions, revision-delta highlights, all individual reviewer reports.

## When to invoke

Called by `run-review-round` after `consolidated.md` is complete. May also be invoked directly when Reviewer main is asked to re-publish an existing consolidated packet (e.g. routing the same decision to a different downstream owner, or re-pinging when an EACN delivery failed). Reviewer main is the only EACN-facing speaker — local subagents do not publish.

## Structure

`consolidated.md` contains: notification, Area Chair / Editor meta-review, exact `## Decision`, required revisions or camera-ready instructions, revision-delta highlights when applicable, all generated reviewer reports. Publish the full content in the EACN task body when feasible; otherwise a concise notification plus the artifact pointer. Decision routes the next action:

| Decision | Next action |
|---|---|
| `Strong Accept` / `Accept` | Camera-ready cleanup |
| `Weak Accept` / `Borderline` | Revision task for Writer + evidence tasks for Expert / Experimenter / Coder as needed |
| `Weak Reject` / `Reject` / `Strong Reject` | Substantial revision or project-level reconsideration before another review round |

## Procedure

1. Verify `artifacts/reviews/round-<n>/consolidated.md` contains notification, AC / Editor meta-review, exact `## Decision`, required revisions or camera-ready instructions, revision-delta highlights when applicable, all generated reviewer reports.
2. Publish through Local EACN. Prefer creating or replying with a task whose body includes the full `consolidated.md` content so downstream roles read one markdown object.
3. If the packet is too large for the EACN message body, include a concise notification plus the artifact pointer `artifacts/reviews/round-<n>/consolidated.md`.
4. Target the action implied by the decision (see table above).
5. Keep Reviewer main as the only EACN-facing speaker.

End with an EACN task / message: review round number, decision, required next action, and either full consolidated markdown or the consolidated artifact path.

## Pitfalls

- Sending only the decision label without the individual reviews.
- Splitting the meta-review and reviewer reports across many messages when one self-contained packet is possible.
- Asking Gru to interpret the decision before Reviewer has published the review packet.
