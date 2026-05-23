---
slug: search-counterexamples
summary: Within an adjudication-instance, enumerate plausible alternative answers and either reject each on evidence or surface the strongest non-rejected as a weakness.
layer: logical
tools:
version: 1
status: active
supersedes:
references: query-reasoning-chain
provenance: human
---

# Skill — Search Counterexamples

A submitted answer is convincing only insofar as the adjacent wrong answers
have been considered and rejected. This skill enumerates them.

## When to invoke

Called by an adjudication-instance whenever the answer space is finite or
small (multiple choice, numeric with bounded precision, named-entity
extraction). Skip only for pure free-form generation where "the space of
alternatives" is unbounded.

## Procedure

1. **Identify the answer space.** Multiple choice: the other letters /
   options. Numeric: ±10%, the order-of-magnitude neighbours, the wrong-unit
   variant. Named entity: the runner-up candidates the submitter might have
   confused for the actual answer.
2. **Enumerate 3-5 alternatives.** Bias toward alternatives a competent
   submitter would actually consider, not random nonsense. If the submission
   discusses one alternative, *include it* in the list rather than skipping it
   — re-test the rejection.
3. **For each alternative, attempt to defend it.** Steel-man the case for the
   alternative being correct. Use `codex` to search the project's exp/ tree
   or external sources for support.
4. **Apply rejection criteria:**
   - Disqualified by a primary source (citation, dataset, formula).
   - Disqualified by unit / sign / domain check.
   - Disqualified by self-consistency with constraints stated in the question.
5. **Output to `aspect-notes/reviewer-<i>-counterexamples.md`**. List each
   alternative with `REJECTED via … | NOT REJECTED, see weakness #N`. A NOT
   REJECTED alternative is a major weakness — surface it loudly.

## When to flip the decision

A NOT REJECTED alternative that is *more plausible* than the submitted answer
flips the verdict to Reject. A NOT REJECTED alternative that is roughly
equally plausible flips to Revise (the team must justify the disambiguator).

## Pitfalls

- Random nonsense alternatives are tells of weak counterexample search; reach
  for the *near misses*.
- Accepting "the submitter rejected this already" without independently
  re-running the rejection.
- Conflating "I cannot find evidence for the alternative" with "the
  alternative is rejected" — the absence of evidence is not the evidence of
  absence in adjudication.
