# Adjudication Summary — Port <port>, Round <n>

Submitted: <ISO timestamp>
Adjudicated: <ISO timestamp>

## Final Verdict

Decision: <Accept | Revise | Reject>
Confidence: <0.0–1.0>
Adjudicator depth: <single | panel>

## Bare Answer (only emitted when Decision = Accept)

<the value of payload.answer, verbatim, with no surrounding prose. This is
the field benchmark harnesses read.>

## Decisive Evidence

- <one-line evidence ref backing the verdict>

## Pointers

- consolidated: branches/shared/reviews/round-<n>/consolidated.md
- adjudicator reports: branches/shared/reviews/round-<n>/reviewer-*.md

This file is written by `mos_adjudicate` after the chair synthesis is
final. Gru reads `bare_answer` (when present) and forwards it to whoever
asked for the final answer; the rest of the file is for audit.
