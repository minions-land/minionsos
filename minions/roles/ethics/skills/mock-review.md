---
slug: mock-review
summary: Run an evidence-angle preview of an artifact as if a reviewer were reading it — without opening a formal review round. Evidence-only; no style or taste criticism.
layer: logical
tools: eacn3_send_message, codex
version: 1
status: active
supersedes:
references: citation-authenticity-audit, evidence-pointer-sweep, delegate-heavy-task
provenance: human
---

# Skill — Mock Review

Run an evidence-angle preview of an artifact as if a reviewer were reading it — without opening a formal review round.

## When to invoke

- Any Role sends a DM asking what a reviewer would say about a concrete artifact.
- A public EACN task is tagged pre-submission-check / review-preview with a named target.
- Wake-up triage surfaces a fresh high-value artifact and no formal review has been requested yet — a proactive preview is warranted.
- **Not** when a formal review round is in flight on the same artifact. The formal round wins; mock-review at that point risks contaminating Reviewer's Pass A isolation.

## Structure

One evidence-angle pass dispatched to a subagent. The subagent enumerates claims, checks cited evidence, and classifies each as `verified` / `unsupported` / `contradicted` / `unclear`. Output lands under `artifacts/ethics/mock-reviews/<slug>.md`. Any informal verdict is explicitly bounded as non-authoritative.

## Procedure

1. **Confirm scope.** A mock-review needs exactly one named target: a paper draft path, an `artifacts/exp-{id}/report.md`, a claim memo, or a specific Writer commit. If the request is vague ("review the project"), reply on EACN asking for a concrete artifact pointer.
2. **Dispatch to subagent.** Prefer the `codex` MCP (see `delegate-heavy-task`); fall back to `Task` on `CODEX_UNAVAILABLE`. Spawn with: artifact path(s), the `mock-review` skill summary, `templates/mock-review.md` as required output format, explicit forbiddens (no writes to `artifacts/reviews/`, no Reviewer personas, no authoritative decision labels, no further reviewer instances), write target `artifacts/ethics/mock-reviews/<slug>.md`.
3. **Subagent enumerates claims.** For each substantive claim, check cited evidence (file path, line number, commit SHA, URL, EACN event id) and classify. Use `citation-authenticity-audit` and `evidence-pointer-sweep` for citation and metric checks.
4. **Subagent writes the preview** using `templates/mock-review.md`. Any informal verdict is prefixed `informal, non-binding, not a Reviewer decision:`.
5. **Verify in main.** Confirm: file landed under `artifacts/ethics/mock-reviews/`, every flagged item has an evidence pointer, no authoritative decision label leaked, no write to `artifacts/reviews/`.
6. **Reply on EACN.** Post a short message to the requester with the file pointer and a one-line headline.

## Pitfalls

- **Drifting into Reviewer's lane.** If you find yourself spawning multiple "reviewer instances" or assigning personas, stop — that is Reviewer's 3-Pass protocol. Mock-review is one evidence-angle pass.
- **Style or taste criticism.** Mock-review is evidence-only. "Section 3 reads awkwardly" is not Ethics' job.
- **Authoritative decision labels.** Never write `## Decision: Reject`. The informal verdict estimates reviewer pressure; it does not deliver a decision.
- **Leaking into formal-review history.** Write only under `artifacts/ethics/mock-reviews/`. Reviewer's Pass A is intentionally history-blind to your previews.
