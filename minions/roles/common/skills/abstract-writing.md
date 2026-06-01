---
slug: abstract-writing
summary: Single-paragraph CNS-style abstract from broad context to result, knowledge delta, and significance — every claim traceable, main result anchored with "Here, we show", closing implication bounded to tested scope.
layer: logical
tools:
version: 4
status: active
supersedes:
references: end-to-end-paper-workflow, citation-audit
provenance: human + SkillTest-R1.C-merged
---

# Skill — Abstract Writing

Constrained narrative ladder in one continuous paragraph: field introduction → related-discipline background → study problem → main result → knowledge delta → broader context. Main result anchored with a direct venue formula. Closing implication bounded to what was actually tested. Every claim traceable.

## When to invoke

- Drafting or rewriting the paper abstract.
- Aligning the abstract with a new main result, revised claim scope, or reviewer-requested framing change.

## Structure

Six rungs of the ladder, each with a strict word budget and a structural anchor:

| Rung | What | Structural anchor |
|---|---|---|
| 1 | Broad context (1–2 sentences, accessible to any scientist) | Field-level motivation, not method mechanics |
| 2 | Technical background (2–3 sentences, related-discipline scientists) | Bridge to the specific subfield |
| 3 | Study problem (1 sentence) | Names the gap the paper addresses |
| 4 | **Main result (1 sentence)** | **Must open `Here, we show` / `Here, we report` / `Here, we introduce` / `In this work we ...`** |
| 5 | Knowledge delta (2–3 sentences) | Quantitative or qualitative comparison vs prior knowledge |
| 6 | **General context (1–2 sentences)** | **Implication bounded to species, scope, and system actually tested** |

The abstract is a single paragraph. The rungs are sentence-level functions inside one block, not paragraph divisions. Do not insert blank lines, section breaks, list formatting, or paragraph breaks inside the abstract.

`We developed ...` / `We performed ...` is NOT acceptable for rung 4 — narrative voice reads as throat-clearing to a venue editor. Use the direct formula even if the source draft uses narrative voice.

For rung 6, name what the paper actually establishes. A mouse preclinical demonstration closes with `establishes a non-viral route for CNS genome editing in mice and defines a platform for further preclinical evaluation`, NOT `supports further evaluation in neurological disease models` — the latter implies disease-utility evidence the paper does not have.

Output lives in `branches/writer/paper/`. Sentence-level support cited in nearby draft comments or notes when claims are non-obvious: `[derived: section <N>]`, `[derived: Expert note <id>]`, `[derived: artifact <path>]`.

## Procedure

1. **Gather claim sources.** Read the current introduction, method summary, results, and Expert notes before drafting. Do not invent motivations, novelty, or implications that are not supported.
2. **Open with broad context** (1–2 sentences, comprehensible to a scientist in any discipline).
3. **Narrow to technical background** (2–3 sentences, comprehensible to scientists in related disciplines).
4. **State the study problem** (1 sentence clearly naming the general problem).
5. **State the main result with the direct formula.** `Here, we show / report / introduce` is the rung-4 anchor; do not substitute narrative voice.
6. **Explain the knowledge delta** (2–3 sentences vs prior knowledge).
7. **Close with bounded implication.** Name the species, scope, and system tested; refuse to imply a translation or disease-utility scope the data do not support.
8. **Merge into one paragraph before delivery.** A freshly drafted multi-section or rung-by-rung abstract must be collapsed into a single continuous block with no internal paragraph breaks.
9. **Audit evidence and length.** Remove unsupported claims, vague impact language, and method detail that crowds out the result. Tighten to the venue's word limit after the structure is complete.

## Pitfalls

- Starting with method mechanics instead of field-level motivation.
- Claiming impact, novelty, or comparison to prior work without manuscript or Expert evidence.
- Burying the main result in background prose, or substituting narrative `We developed` for the direct `Here, we show` formula.
- Abstract split into multiple paragraphs (a freshly drafted multi-section abstract must be merged into a single block before delivery).
- Closing on disease utility / clinical translation when the data are mouse / cell / in-vitro only.
- Writing only for specialists when the venue expects broad scientific readability.
