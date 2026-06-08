---
slug: mock-review
summary: Run an evidence-angle preview of an artifact as if a reviewer were reading it — without opening a formal review round. Evidence-only; dispatched as a single Workflow agent (or pipeline for >50KB artifacts); no style or taste criticism.
layer: logical
tools: eacn3_send_message, mos_publish_to_shared, Workflow
version: 2
status: active
supersedes:
references: citation-authenticity-audit, evidence-pointer-sweep, role-act-via-workflow
provenance: human
---

# Skill — Mock Review

Run an evidence-angle preview of an artifact as if a reviewer were
reading it — without opening a formal review round.

## When to invoke

- Any Role sends a DM asking what a reviewer would say about a concrete artifact.
- A public EACN task is tagged pre-submission-check / review-preview with a named target.
- Wake-up triage surfaces a fresh high-value artifact and no formal review has been requested yet — a proactive preview is warranted.
- **Not** when a formal review round is in flight on the same artifact. The formal round wins; mock-review at that point risks contaminating formal review Pass A isolation.

## Structure

One evidence-angle Workflow (`single-agent` for < 50 KB, `pipeline`
otherwise). The Workflow agent enumerates claims, checks cited
evidence, and classifies each as `verified` / `unsupported` /
`contradicted` / `unclear`. Draft output lands under
`branches/ethics/mock-review-<slug>.md`; the main role publishes it
to `branches/shared/ethics/mock-review-<slug>.md` via
`mos_publish_to_shared`. Any informal verdict is explicitly bounded
as non-authoritative.

## Procedure

1. **Confirm scope.** A mock-review needs exactly one named target: a paper draft path, an `branches/shared/exp/exp-<id>/report.md`, a claim memo, or a specific Expert commit. If the request is vague ("review the project"), reply on EACN asking for a concrete artifact pointer.
2. **Dispatch the Workflow.** Choose `single-agent` for < 50 KB targets, `pipeline` otherwise (claim-enumeration → evidence-check → classification). Spec includes: artifact path(s), the `mock-review` skill summary, `templates/mock-review.md` as required output format, explicit forbiddens (no writes to `branches/shared/reviews/`, no formal-review personas, no authoritative decision labels, no reviewer instances), write target `branches/ethics/mock-review-<slug>.md`, the §10.1 scratchpad fragment, and the size-bounded return schema (≤ 5 KB total).
3. **Workflow agent enumerates claims.** For each substantive claim, check cited evidence (file path, line number, commit SHA, URL, EACN event id) and classify. Use `citation-authenticity-audit` and `evidence-pointer-sweep` for citation and metric checks.
4. **Workflow agent writes the preview** using `templates/mock-review.md`. Any informal verdict is prefixed `informal, non-binding, not a formal review decision:`.
5. **Verify in main.** Confirm: file landed under `branches/ethics/`, every flagged item has an evidence pointer, no authoritative decision label leaked, no write to `branches/shared/reviews/`.
6. **Publish and reply.** Publish to `branches/shared/ethics/mock-review-<slug>.md` via `mos_publish_to_shared`, then post a short EACN message to the requester with the shared file pointer and a one-line headline.

## Pitfalls

- **Drifting into the formal review workflow.** If you find yourself spawning multiple reviewer instances or assigning personas, stop — that belongs to the `mos_review_run` 3-pass protocol. Mock-review is one evidence-angle pass.
- **Style or taste criticism.** Mock-review is evidence-only. "Section 3 reads awkwardly" is not Ethics' job.
- **Authoritative decision labels.** Never write `## Decision: Reject`. The informal verdict estimates reviewer pressure; it does not deliver a decision.
- **Leaking into formal-review history.** Publish only under `branches/shared/ethics/` with the flat `mock-review-<slug>.md` name. Formal review Pass A is intentionally history-blind to your previews.
