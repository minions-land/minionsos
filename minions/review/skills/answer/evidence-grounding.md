---
slug: evidence-grounding
summary: For each external-fact claim in the submitted reasoning_summary, confirm or refute against a primary source; flag unmarked claims for ethics-style audit.
layer: logical
tools:
version: 1
status: active
supersedes:
references: query-reasoning-chain, search-counterexamples
provenance: human
---

# Skill — Evidence Grounding

Adjudication is downstream of fact-checking. Before debating *whether* a
chain of inferences is correct, confirm each *external* claim the chain rests
on actually says what the submitter says it says.

## When to invoke

Called by an adjudication-instance for any submission whose reasoning leans
on external sources: citations, dataset values, code outputs from a third
script, statistics from a paper, definitions from a textbook. Skip only for
purely mathematical proofs where the only "external" facts are axioms.

## Procedure

1. **Enumerate external claims** from `payload.reasoning_summary`. Each claim
   has the shape *<source> says <fact>*.
2. **For each claim, retrieve the primary source.** Use `codex` for paper
   downloads (`mos_download_arxiv`, etc.) and for chasing references.
   Workspace files first, then web.
3. **Compare verbatim.** Quote the source. Mark CONFIRMED only if the source
   *literally* contains the fact; REFUTED if the source contradicts; PARTIAL
   if the source contains a weaker / stronger / off-by-one variant.
4. **Mark UNGROUNDED** for claims the submitter made without naming a source,
   when those claims are load-bearing.
5. **Output to `aspect-notes/reviewer-<i>-evidence-grounding.md`** using
   `templates/aspect-note.md`. Each row: claim → source → verdict → quote.

## When to flip the decision

REFUTED on a load-bearing claim → Reject. PARTIAL on a load-bearing claim →
Revise (the team must restate to match the source). UNGROUNDED claims are
surfaced as weaknesses; multiple UNGROUNDED claims also push to Revise.

## Pitfalls

- Accepting paraphrased citations without checking the source. Paraphrase is
  where claim drift hides.
- Treating "I could not access the source" as CONFIRMED. Mark UNVERIFIED and
  surface the access blocker instead.
- Spending the budget on every minor citation; prioritise *load-bearing*
  external claims (the ones whose status changes the answer).
