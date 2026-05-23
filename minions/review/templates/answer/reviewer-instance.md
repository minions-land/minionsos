# Adjudicator <i> Report (Answer)

Round: <n>
Adjudicator instance: <i of 1-3>
Reviewed target: branches/shared/submissions/answer.json
History isolation: no peer adjudicator reports consulted before drafting weaknesses

## Submission Restated

- **Submitted answer:** <verbatim or canonicalised value of payload.answer>
- **Stated reasoning summary:** <one-line restatement of payload.reasoning_summary, or `none provided`>
- **Stated confidence:** <payload.confidence, or `none stated`>

## Reasoning-Chain Audit

<For each load-bearing inference step in the submitted reasoning_summary, mark
one of: VERIFIED (independently re-derived), UNVERIFIED (could not re-derive
in the time available), or BROKEN (specific counter-derivation found). Cite
the artefact / equation / source that supports the verdict.>

- step 1: <verdict> — <evidence>
- step 2: <verdict> — <evidence>
- ...

## Counterexample Search

<List the alternative answers considered and why each was rejected. If no
alternative was considered by the submitter, propose at least one and either
accept or reject it here.>

- candidate: <alt answer> — <rejected because … | NOT REJECTED, see weakness #N>

## Self-Consistency Check

<Re-derive the answer by an independent path (different unit conversion,
different formula, different quote, different code path). State whether the
re-derivation matches.>

- independent path: <description>
- re-derived value: <value>
- matches submitted: <yes | no | partial>

## Evidence Grounding

<For each claim the submitted reasoning_summary makes about external facts
(citations, code outputs, dataset values), confirm or refute. Mark unmarked
claims for Ethics-style audit.>

- claim: <restatement> — <CONFIRMED via … | REFUTED by … | UNGROUNDED>

## Major Weaknesses

- <evidence-backed weakness; tie each to a step / counterexample / claim above>

## Questions That Would Resolve Doubt

- <specific, narrow question whose answer would flip or pin this adjudicator's verdict>

## Decision

<Accept | Revise | Reject>

Confidence: <0.0–1.0>
Rationale: <one sentence linking the decision to the strongest weakness or confirmation above>
