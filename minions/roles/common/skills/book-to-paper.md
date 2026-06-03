---
slug: book-to-paper
summary: Generate a compilable LaTeX paper from a project Book (the main-branch knowledge package). Maps Book layers to paper sections in the fixed order abstract→introduction→related work→methodology→experiments→conclusion, then drives the writer/latex/figure skills to draft, typeset, and compile. The reverse of compiling a paper into a Book.
layer: logical
tools:
version: 2
status: active
supersedes:
references: end-to-end-paper-workflow, make-latex-model, paper-compile, abstract-writing, introduction-discipline, related-work-discipline, methodology-discipline, conclusion-limitation, latex-typography, academic-plotting, figure-spec, citation-audit, paper-quality-contract
provenance: human-directed (P5 rebuild); hardened by round-1 real-data validation on the ResNet (Book, ground-truth paper) pair — modality/scope/caption/trajectory honesty rules + venue-shape/figure deltas
---

# Skill — Book → Paper

Generate a submission-shaped LaTeX paper from a project **Book** (the
main-branch knowledge package: `Book.md` + `logic/` + `src/` + `evidence/` +
`draft/`). This is the inverse of compiling a paper *into* a Book: the Book
already holds the falsifiable claims, the exact evidence tables/figures, the
method, and the exploration trace — your job is to render that structured
knowledge back into a flowing, venue-shaped manuscript **without inventing
anything that is not already grounded in the Book**.

> **Production note.** In live MinionsOS projects, paper writing is
> **human-driven** (Gru drives, with the human in the loop). This skill is the
> engine that powers that — and it is *also* run fully end-to-end (no human)
> during capability validation, to measure and harden the Book→Paper gap.

## When to invoke

- A project's Book has matured (claims verified by Ethics, evidence landed)
  and Gru/the human wants a manuscript draft.
- During Book→Paper **capability validation**: generate from a known Book,
  compare against a ground-truth paper, iterate.

## The one hard rule: every sentence traces to the Book

The Book is the single source of truth. A claim in the paper must correspond
to a `logic/claims.md` entry; a number must come from `evidence/`; a method
detail from `logic/solution/` or `src/`. If the Book does not support a
sentence, you do not write it — you flag the gap. This is what keeps the
generated paper honest (no over-claim) and is the property validation checks.

### Source provenance lives in `%` comments, never in the rendered PDF

Every `sections/*.tex` file carries its Book provenance as **LaTeX comment
lines (`%`) at the top of the section and inline next to non-obvious claims**.
This is a hard requirement of the Book→Paper contract:

- **The provenance is for the author + Ethics audit, not the reader.** It
  records which Book sources (`problem.md`, claim ids `C01-C03`, `evidence/`
  table ids, `reel_ref` pointers) each passage was derived from, so any
  sentence can be traced back to its grounding when the paper is audited or
  revised.
- **`%`-commented lines are stripped by the LaTeX compiler** — they never
  reach `paper.pdf`. A reviewer or a published reader sees only the prose; the
  source index is invisible to them. This is deliberate: the manuscript must
  read as a normal paper, the provenance must survive in the `.tex` (and thus
  in git history), and the two must never mix.
- **Never render provenance as visible text** — no "(Source: claims.md C01)"
  in the body, no footnote citing a Book path, no `\todo{}` that typesets. If
  it traces to the Book rather than to a `\cite`d external reference, it goes
  in a `%` comment.

Standard shape at the top of each `sections/<name>.tex`:

```latex
% [VERIFY] <section> -- <Book sources: problem.md O1-O5, Book.md overview, claims C01-C03>
% <MODALITY/SCOPE GUARD: any honesty constraint carried from the Book, e.g.
%  "degradation->optimization is argue/unlikely, NOT ruled out (C01 interp, O3)">
\section{...}
```

Inline, next to a specific claim whose grounding is not obvious:

```latex
% claims.md C08 + evidence/tables/table3 (exact top-1 numbers, do not round)
a 152-layer residual net ... has $3.57\%$ top-5 error ...
```

The coverage report (step 6) is the *machine-checkable* ledger; these
`%` comments are the *in-place* ledger a human editor reads while revising the
`.tex` directly. Both are required — they serve different readers.

### Honesty sub-rules (round-1 validation hardened these)

These are the specific ways a Book→Paper run drifts into over-claim. Each is a
hard check, not a suggestion:

1. **Preserve epistemic modality — never escalate.** Carry the Book's own
   hedging verbs into the paper. If `claims.md` says *argue / suggest /
   indicate / unlikely / consistent with / "do not formally prove"*, the paper
   may use {argue, suggest, indicate, is unlikely to be, consistent with}. It
   may **not** escalate to {ruled out, proven, established, eliminated as a
   cause, demonstrates}. (Round-1 defect: intro wrote "can be ruled out" where
   the Book said "argue … unlikely".) Also: a claim's modality in the
   Abstract/Intro must match its restatement in Limitations — flag any
   contradiction.
2. **Scope reconciliation before sign-off.** Diff `Book.md` frontmatter
   (abstract + claims_summary) against `logic/claims.md`. Any headline asserted
   in the abstract but absent from `claims.md` must be **either** surfaced in
   the paper **or** explicitly logged in the coverage report as an intentional
   out-of-scope drop — never silently truncated. **List-truncation guard:**
   when the Book enumerates a list ("won 1st on A, B, C, D"), surface the full
   enumeration or flag the omission; never keep item 1 and drop the tail.
3. **Caption fidelity.** When an `evidence/` table's `**Caption**:` carries a
   methodological qualifier ("VGG-16 is based on our test", "best mean±std over
   5 runs", "† reported on the test set"), the rendered `\caption` MUST preserve
   it verbatim — those qualifiers are part of the evidence's meaning. A
   "Source: Table N" tail may be added but qualifiers may not be dropped.
4. **Trajectory-evidence rule.** A dynamic/temporal claim ("throughout
   training", "converges faster from the start", "lies below … throughout")
   backed only by an **endpoint** table (not per-iteration data) must be hedged
   ("the underlying analysis reports …") AND flagged as a missing-curve Book
   gap — never stated as if a rendered curve shows it. An endpoint figure may
   not stand in for a trajectory figure without a caption disclaimer + a prose
   hedge.

## Venue & format shaping (round-1 validation hardened this)

The paper's *shape* must match the venue, not default to a single-column
report. Drive it from `Book.md` frontmatter:

- **Format selector.** Read `venue:` / `domain:`. For CV/ML conference venues
  (CVPR/NeurIPS/ICML/ICLR/arXiv-CS) emit a **two-column** class
  (`\documentclass[10pt,twocolumn]{article}` or the venue style if available),
  not a single-column 11pt `article`. (Round-1 defect: produced a generic
  single-column report for a CVPR-class paper.)
- **Conceptual / schematic figures, not just data plots.** `academic-plotting`
  renders the *evidence-table numbers*; you ALSO owe the method's signature
  diagrams. For each component graph in `logic/solution/architecture.md` and
  each block in `logic/solution/algorithm.md`, emit a TikZ/diagram figure (e.g.
  the residual-block schematic, the architecture-column diagram). The method's
  defining visual must be reproduced, not downgraded to an algorithm listing.
- **Appendix tier.** `methodology-discipline` moves implementation substrate,
  secondary baselines, and extended tables out of the body — realize that with
  an actual `\appendix`. Don't drop the deeper evidence tables; route them to
  the appendix.
- **Contributions rendering.** Match the venue norm: older-conference
  reconstructions use flowing-prose contributions, not an `itemize` list.
- **Reference completeness.** If the rendered `references.bib` is materially
  shorter than a venue-typical bibliography, the coverage report flags it
  (bounded by `related_work.md`) rather than silently under-citing.

## Book layer → paper section map

Default section order (override only for a venue that demands it, e.g. Nature
methods-last):

**abstract → introduction → related work → methodology → experiments → conclusion**

| Paper section | Primary Book sources | Writer skill |
|---|---|---|
| **Abstract** | `Book.md` frontmatter (abstract, claims_summary) | `abstract-writing` |
| **Introduction** | `logic/problem.md` (observations→gaps→insight), `Book.md` overview, top 2-3 `logic/claims.md` headline claims | `introduction-discipline` |
| **Related work** | `logic/related_work.md` (typed dependency graph) | `related-work-discipline` |
| **Methodology** | `logic/solution/{architecture,algorithm,constraints,heuristics}.md`, `logic/concepts.md`, `src/configs/`, `src/environment.md` | `methodology-discipline` |
| **Experiments** | `logic/experiments.md` (the plans), `evidence/tables/*`, `evidence/figures/*` (the exact numbers), the claims each experiment verifies | `academic-plotting`, `figure-spec`, table rendering |
| **Conclusion** *(conditional)* | `logic/problem.md` key insight, headline `logic/claims.md`, `logic/solution/constraints.md` (limitations), `draft/` dead-ends (honest limitations / future work) | `conclusion-limitation` |

**Conclusion is conditional, not mandatory.** If the venue/source convention
omits a standalone conclusion (some CV/ML conference papers fold the wrap-up
into the final Experiments paragraph), do that instead of always appending a
Conclusion + Limitations + Future Work block. Match the venue.

Cross-layer binding to preserve: a claim cited in the text → its
`experiments.md` plan → its `evidence/` table/figure. The Book already wires
these (claim Proof → E-id → evidence); carry the linkage into the paper so
Experiments numbers back the Introduction claims.

## Procedure

Run as a Workflow (`pipeline` shape) per common §4 — one stage per section so
each gates the next and the final return is a compiled PDF + a coverage report.

1. **Read the Book.** Load `Book.md` (manifest), then `logic/problem.md`,
   `logic/claims.md`, `logic/related_work.md`, `logic/solution/*`,
   `logic/experiments.md`, `logic/concepts.md`, `src/configs/*`,
   `src/environment.md`, and the `evidence/` index + every table/figure file.
   Build a claim→experiment→evidence map (the Book's cross-layer bindings).
2. **Seed the LaTeX skeleton.** Use `make-latex-model` to lay down
   `branches/<role>/paper/main.tex` + `sections/*.tex` + `references.bib` +
   `figures/`. One `sections/<name>.tex` per section in the fixed order.
3. **Draft each section** (apply the mapped writer skill). As you write each
   `sections/<name>.tex`, open it with the `% [VERIFY] ...` provenance header
   and drop inline `%` source comments next to non-obvious claims (see "Source
   provenance lives in `%` comments" above — these are stripped from the PDF):
   - *Abstract* — distill `Book.md` abstract + claims_summary; ≤ ~200 words.
   - *Introduction* — `problem.md` arc (observation → gap → insight), state
     the headline contributions = the top claims, forward-reference evidence.
   - *Related work* — render `related_work.md` typed edges (imports / extends /
     bounds / baseline / refutes) into prose with `\cite`s; build the matching
     `references.bib` entries from the Book's citation keys/DOIs.
   - *Methodology* — `solution/architecture.md` (component graph) +
     `algorithm.md` (math + pseudocode) + `concepts.md` definitions +
     `constraints.md`; pull exact hyperparameters from `src/configs/`.
   - *Experiments* — for each `experiments.md` plan, render its `evidence/`
     table(s)/figure(s) with **exact numbers** (never rounded/invented), state
     which claim each result supports. Use `academic-plotting` / `figure-spec`
     for figures and the table-layout rules in `latex-typography`.
   - *Conclusion* — summarize verified claims, state limitations from
     `constraints.md` + honest dead-ends from `draft/`.
4. **Wire citations + figures/tables.** Every `\ref`/`\cite` resolves; every
   `evidence/` artifact the text mentions is rendered; run `citation-audit`.
5. **Compile + typeset.** Drive `paper-compile` (latexmk, ≤3 fix iterations,
   overfull-hbox + macro-discipline lint) and `latex-typography`. Output a real
   `paper.pdf`.
6. **Coverage report.** Emit `book_to_paper_coverage.md`: every paper claim →
   its Book claim id; every number → its `evidence/` source; list any
   paper sentence with **no Book grounding** (should be empty) and any Book
   claim **not** surfaced in the paper (gaps). This is the honesty ledger.

## Anti-patterns (these are the failure modes validation hunts)

- **Over-claim**: stating a result stronger than the Book's `claims.md`
  Statement / Evidence basis supports. The Book's scope is the ceiling.
- **Invented numbers**: any metric not traceable to an `evidence/` file.
- **Dropped evidence**: a verified Book claim with strong evidence omitted
  from Experiments.
- **Markdown-as-paper**: a `.md` is never the deliverable — only a compiled
  `paper.pdf` from real LaTeX (see `paper-compile`).
- **Fabricated citations**: every `\cite` must map to a real `related_work.md`
  entry with a DOI/key (Ethics audits this).
- **Visible provenance**: a Book source index ("Source: claims.md C01",
  "see evidence/table3") rendered as body text, a footnote, or any typeset
  element. Provenance is `%`-commented only — it must not reach the PDF.
- **Missing provenance**: a `sections/*.tex` with no `% [VERIFY]` header, or a
  non-obvious claim with no inline `%` source comment. Untraceable prose is a
  defect even when it happens to be correct.

## Validation protocol (how this skill earns trust — 实践出真理)

This skill is NOT trusted on assertion. Before it is relied on in production it
must be measured on real **(Book, ground-truth paper)** pairs:

1. Take a published paper with a known Book (e.g. compile a paper into our Book
   format, or use a hand-built Book example).
2. Run this skill **end-to-end (no human)** from the Book → `paper.pdf`.
3. Compare generated vs ground-truth on concrete axes: claim coverage (did we
   surface every headline claim?), evidence fidelity (do our tables match the
   real numbers exactly?), section completeness, scope calibration (no
   over/under-claim vs the original), and compile/typography quality.
4. Record the gap, improve the writer skills + this mapping, regenerate.
   **Iterate until the gap converges**; only then is the skill "landed".
5. Keep each round's coverage report + comparison as evidence — never report
   "it works" without the measured comparison.

