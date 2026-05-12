# Skill — Citation Audit

Verify every `\cite{...}` in the paper is a real work, correctly attributed, and used in a context the cited paper actually supports.

## Core move

For each bib entry, independently check three layers: the work **exists**, the **metadata** matches canonical sources, and the **context** in our sentence is something the cited paper actually establishes. This is the bibliographic arm of root §9 evidence-first.

## Procedure

1. **Gate timing.** Run after the draft is stable and numeric claims have been audited; before final compile for submission. Running too early wastes lookups on placeholder text.
2. **Extract (key, context) pairs.** For every `\cite{...}` in `branches/writer/paper/`, record the key, file, line, and the full surrounding sentence. Build the inverse index (bib entry → cite sites).
3. **Verify existence.** For each entry: resolve the arXiv ID / DOI / venue URL via web search. If it doesn't resolve, flag `MISSING`.
4. **Verify metadata.** Compare authors, year, title, venue to DBLP / arXiv / ACL Anthology / OpenReview / publisher. Flag `DRIFT` on any mismatch. Watch for arXiv v1 vs conference version title drift and year off-by-one on preprint-to-accepted transitions.
5. **Verify context.** For each cite site, ask: does the cited paper actually support what our sentence claims it supports? Wrong-context citations (real paper, wrong claim) are the most dangerous class — e.g. citing a method to support the opposite of what it argues. Flag `WRONG_CONTEXT` with a one-line explanation.
6. **Record verdicts.** Write `branches/writer/paper/CITATION_AUDIT.md` (human) and `branches/writer/paper/CITATION_AUDIT.json` (machine): per-entry `{key, status ∈ OK|DRIFT|MISSING|WRONG_CONTEXT, evidence_url, notes}`.

## When to invoke

- Once before any submission, rebuttal, or camera-ready.
- When Reviewer flags a suspect citation in `artifacts/reviews/`.
- When adding a batch of new citations late in the writing cycle.

## Pitfalls

- Pattern-matching from memory. Every verdict must cite a fresh web source; memory-only claims violate root §9.
- Auto-"fixing" by swapping in a different paper without rechecking the context.
- Treating existence as sufficient — wrong-context is the failure mode that survives naïve audits.

## Output habit

`CITATION_AUDIT.md` lists every `\cite` key with verdict + evidence URL + the sentence it appeared in. Every non-`OK` entry is marked `[derived: web lookup <URL> @ <ts>]` per root §9, so downstream agents can audit the audit.
