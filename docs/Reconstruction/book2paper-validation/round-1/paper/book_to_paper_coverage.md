# Book → Paper Coverage Report

**Artifact:** `Deep Residual Learning for Image Recognition` (ResNet, He et al. 2015)
**Book source:** hand-built Book of the ResNet paper (local validation fixture)
**Generated paper:** `round-1/paper/main.pdf` (13 pages, compiled with `latexmk -pdf`, TeX Live 2026)
**Run:** Book→Paper capability validation, round 1, fully end-to-end (no human in the loop)

## Verdict summary

- **Claim coverage:** 8 / 8 falsifiable claims (C01–C08) surfaced in the paper.
- **Number fidelity:** every numeric value in the body traces to an `evidence/` table (or `Book.md`/`logic/`); no value was rounded or invented. Spot-checked exhaustively below.
- **Ungrounded sentences:** none found. Every assertion maps to a `claims.md` Statement, a `problem.md` Observation/Insight, a `solution/*` detail, or an `evidence/` number. Interpretive/connective sentences reuse the Book's own `Interpretation` fields.
- **Honest gaps:** Figures 1/4/6/7 of the Book are *qualitative figure-summaries with no tabulated per-iteration data* — they are described in prose (grounded in the figure-summary text) but NOT reproduced as plotted curves, because doing so would require fabricating per-iteration points. Three new figures were rendered instead, entirely from exact table numbers. A handful of implementation-substrate hyperparameters (exact iteration budgets) were left at body level rather than spun into an appendix. Details in §5–§6.

<!-- BODY-BELOW -->

## 1. Claim → paper-section map (C01–C08)

Every headline claim from `logic/claims.md` is surfaced. The "Where in paper" column gives
the section; the "Evidence rendered" column lists the table/figure that backs it.

| Book claim | Statement (abridged) | Where in paper | Evidence rendered | Status |
|---|---|---|---|---|
| **C01** | Plain CNNs degrade with depth (training error ↑ with depth) | Abstract; Intro ¶1–2; §Exp 4.1 | Table 2 (`tab:plainvsres`), Fig. `fig:plainvsres`; prose from Fig. 4/6 summaries | Covered |
| **C02** | Residual learning eliminates degradation (ResNet-34 > ResNet-18, > plain-34) | Abstract; Intro contrib. 2; §Method 3.1; §Exp 4.1 | Table 2, Table 3, Fig. `fig:plainvsres` | Covered |
| **C03** | Accuracy grows with depth to 152 layers; lower complexity than VGG | Abstract; Intro contrib. 2/3; §Exp 4.3 | Table 1, Table 3 (`tab:imagenetfull`), Table 4, Table 5, Fig. `fig:resnetdepth` | Covered |
| **C04** | Identity shortcuts suffice; projection gives marginal gains; C rejected | §Method 3.2/3.3; §Exp 4.2 | Table (`tab:shortcut`), derived subset; Table 3 rows A/B/C | Covered |
| **C05** | Bottleneck blocks make 50/101/152-layer nets practical | §Method 3.3; §Exp 4.3 | Table 1 (FLOPs), Table 3 | Covered |
| **C06** | Generalizes to CIFAR extreme depth (110; 1202 trains, overfits) | Abstract; Intro contrib. 4; §Exp 4.4 | Table 6 (`tab:cifar`), Fig. `fig:cifar` | Covered |
| **C07** | Warmup needed for 110-layer CIFAR ResNet | §Exp 4.4 | Table 6 (prose: warmup recipe from `src/configs/training.md`) | Covered |
| **C08** | ResNet-101 transfer → large COCO/VOC detection gains over VGG-16 | Abstract; Intro contrib. 4; §Exp 4.5 | Table (`tab:detection`) = Tables 7+8 | Covered |

## 2. Number → evidence-source ledger (exact-match audit)

Every number printed in the paper body/tables, with its `evidence/` (or `logic/`/`src/`)
source. All verified equal to source — **no rounding, no invention**.

| Number(s) in paper | Paper location | Source file | Source value |
|---|---|---|---|
| plain-18 27.94, plain-34 28.54, ResNet-18 27.88, ResNet-34 25.03 | Abstract, Intro, §4.1, Table 2, Fig. plainvsres | `evidence/tables/table2_imagenet_plain_vs_residual.md` | 27.94 / 28.54 / 27.88 / 25.03 |
| 3.51 pts (34 vs plain-34), 2.85 pts (34 vs 18) | §4.1 | `logic/claims.md` C02 Evidence basis | "better than plain-34 by 3.51 pts … by 2.85 pts" |
| VGG-16 28.07/9.33, GoogLeNet –/9.15, PReLU 24.27/7.38, plain-34 28.54/10.02 | Table 3 | `evidence/tables/table3_imagenet_validation_full.md` | identical rows |
| ResNet-34 A 25.03/7.76, B 24.52/7.46, C 24.19/7.40 | Table 3, Table shortcut, §4.2 | `table3_…` + `derived_from_table3_shortcut_options.md` | identical |
| ResNet-50 22.85/6.71, 101 21.75/6.05, 152 21.43/5.71 | Table 3, Fig. resnetdepth, §4.3 | `table3_imagenet_validation_full.md` | identical |
| Δ vs plain-34: −3.51 / −4.02 / −4.35 | Table shortcut, §4.2 | `derived_from_table3_shortcut_options.md` | −3.51 / −4.02 / −4.35 |
| 0.84 top-1 (A↔C span) | §4.2 | derived: 25.03 − 24.19 = 0.84 (arithmetic on Table 3) | computed, exact |
| Single-model 19.38/4.49 (152) + all Table 4 rows | Table 4, §4.3 | `evidence/tables/table4_imagenet_singlemodel.md` | identical |
| Ensemble 3.57; baselines 7.32/6.66/6.8/4.94/4.82 | Abstract, §4.3, Table 5 | `evidence/tables/table5_imagenet_ensembles.md` | identical |
| CIFAR 8.75/7.51/7.17/6.97/6.43(6.61±0.16)/7.93; params 0.27–19.4M; baselines | Table 6, Fig. cifar, §4.4 | `evidence/tables/table6_cifar10.md` | identical |
| 1202 training error <0.1% | §4.4, Conclusion | `logic/claims.md` C06; `trace` N13 | "training error <0.1%" |
| warmup: LR 0.01 ~400 iters until train err <80%, restore 0.1 | §4.4 | `src/configs/training.md`; `logic/claims.md` C07; `solution/constraints.md` | identical recipe |
| VOC 73.2→76.4, 70.4→73.8 | Table detection, §4.5 | `evidence/tables/table7_pascal_voc_detection.md` | identical |
| COCO 41.5→48.4 (mAP@.5), 21.2→27.2 (mAP@[.5,.95]) | Abstract, §4.5, Table detection | `evidence/tables/table8_coco_detection.md` | identical |
| 6.0 pt absolute / 28% relative (COCO) | Abstract, §4.5, Conclusion | `logic/claims.md` C08 ("6.0-point absolute (28% relative)") | identical |
| FLOPs 1.8/3.6/3.8/7.6/11.3 ×10⁹; VGG-19 19.6 | Abstract, §3.3, Table 1, §4.3 | `evidence/tables/table1_imagenet_architectures.md` | identical |
| block counts 2/3/3/3/3 … 2/6/6/23/36 … | Table 1, §3.3 | `table1_…` + `solution/architecture.md` | identical |
| "8× deeper than VGG" | Abstract, Intro, §4.3 | `Book.md` overview / `solution/architecture.md` ("≈8× deeper") | identical |
| "3× more iterations did not close gap" | Conclusion (limitations) | `trace/exploration_tree.yaml` N05 | identical |
| mini-batch 256 (ImageNet)/128 (CIFAR), momentum 0.9, wd 1e-4 | §3.4 | `src/configs/training.md` | identical |
<!-- BODY-BELOW-2 -->

## 3. Related-work / citation provenance

`references/references.bib` (26 entries) is built entirely from `logic/related_work.md`
(RW01–RW12 plus the "Briefer citations" list). Every `\cite` in the body resolves to a bib
entry, and every bib entry is cited (bidirectional check passed: 0 `MISSING`, 0 `ORPHAN_BIB`
in the final compile — `main.log` shows 0 undefined citations, all 26 `\bibitem`s emitted).
Typed edges from `related_work.md` are preserved in the Related Work prose:

| Book RW | Type | Rendered as |
|---|---|---|
| RW01 Highway | refutes (gating) | "reject the gating mechanism … parameter-free identity shortcut that is never closed" |
| RW02 VGG | baseline | "adopt these [VGG] rules but reach far greater depth at much lower complexity" |
| RW03 BatchNorm | imports | "imported wholesale and applied identically to plain and residual variants" |
| RW04 MSRA init | imports | "variance-preserving initialization for rectifiers" |
| RW05 GoogLeNet | baseline | "comparison point rather than … architectural ingredient" |
| RW06 PReLU-net | baseline | Table 3/4 baseline rows + "surpassing every prior single model" |
| RW07 BN-inception | baseline | Table 4/5 baseline rows |
| RW08 residual representations | extends | "carry the principle into deep learning … learned rather than engineered" |
| RW09 multigrid/preconditioning | extends | "reformulating the system in terms of residual variables" |
| RW10 Faster R-CNN | imports | "build on the Faster R-CNN detection framework … keeping the pipeline fixed" |
| RW11 NoC | imports | "sharing full-image conv features and treating a late conv stage as the per-region classifier" |
| RW12 datasets | imports | PASCAL VOC / ImageNet / COCO / CIFAR cites |

**Citation-audit honesty note (no live web lookup performed):** this is an offline
end-to-end generation run. The bib metadata was transcribed from `related_work.md`'s stated
authors/years/venues, not verified against Crossref/DOI resolvers as a production
`citation-audit` sweep requires. The Book itself is a reconstruction whose DOIs are partly
given as arXiv ids / paper ref-numbers (e.g. "ref [16]"), so a few venue strings are the
canonical-but-unverified values implied by the Book (e.g. BN-Inception → ICML 2015). No bib
key was invented beyond what `related_work.md` names. Flagged for a real `citation-audit`
pass before any non-validation use.

## 4. Ungrounded-sentence audit (the honesty test)

Method: each body paragraph was checked sentence-by-sentence against a Book source. Result:
**no ungrounded sentences.** Categories of sentence and their grounding:

- **Result statements** → exact `evidence/` numbers (ledger §2).
- **Mechanism/method** → `solution/algorithm.md` (Eqn. 1/2, pseudocode → `alg:block`),
  `solution/architecture.md` (stages, stem, head, bottleneck), `logic/concepts.md`
  (residual mapping, identity/projection shortcut, bottleneck, BN, plain net).
- **Motivation/insight** → `logic/problem.md` O1–O5, G1–G2, Key Insight, A1.
- **Interpretive/connective clauses** ("reflects an optimization difficulty", "attributable
  to the learned representation", "stability aid rather than a fundamental requirement") →
  reuse the Book's own `Interpretation` fields in `claims.md` and the `why_failed`/`rationale`
  fields in the trace. None exceed the Book's stated interpretation.
- **Scope-bounding clauses** (no formal proof; ensemble not single-model-reproducible;
  protocols not mixable) → `solution/constraints.md` "Out-of-scope" + "Generalization
  caveats" + "Unverified hypothesis".

No sentence asserts a result stronger than its `claims.md` Statement (no over-claim), and the
Conclusion deliberately carries no citations and no numbers (per `conclusion-limitation`).

## 5. Anti-pattern self-check (the failure modes validation hunts)

| Anti-pattern | Status in this run |
|---|---|
| Over-claim beyond `claims.md` | None. Each claim's wording is bounded to its Statement; e.g. optimization-easing is stated as "supported empirically … not formally proven" (C02 Interpretation + constraints.md). |
| Invented numbers | None. Ledger §2 traces every number; the only computed value (0.84 = 25.03−24.19) is exact arithmetic on Table 3, flagged as derived. |
| Dropped evidence | None of the 8 raw tables omitted: Tables 1,2,3,4,5,6,7,8 + derived subset all rendered. See §6 for figures. |
| Markdown-as-paper | Deliverable is a compiled `paper.pdf` from real LaTeX. |
| Fabricated citations | None invented; all from `related_work.md`. Metadata-verification deferred (see §3). |

## 6. Honest gaps and deviations

1. **Book figures 1, 4, 6, 7 are not reproduced as plotted curves.** Each
   `evidence/figures/*.md` explicitly states "per-iteration values are not tabulated by the
   paper" and gives only qualitative shape. Plotting them would require fabricating data
   points, which violates the hard rule. **Decision:** describe their qualitative content in
   prose (grounded in the figure-summary text — e.g. "plain-34 sits above plain-18 throughout
   optimization") and instead render three NEW figures (`fig:plainvsres`, `fig:resnetdepth`,
   `fig:cifar`) built entirely from exact table numbers. Fig. 7's layer-response analysis is
   carried as the prose motivation in §3.1/Conclusion (its interpretation), not as a plot.
2. **Figure provenance.** The three generated figures read their numbers from
   `figures/data/*.csv`, each csv headed with the exact `evidence/tables/*` source. Scripts
   (`figures/gen_fig_*.py`) follow `academic-plotting` (rcParams, palette, post-save
   Type-42 font gate — all three pass, 0 Type-3 fonts).
3. **Body vs appendix split not fully applied.** `methodology-discipline` asks that
   implementation substrate (exact iteration budgets, batch sizes, config identifiers) move to
   an appendix. This run kept a compact "Implementation and training" subsection (§3.4) at body
   level and used `\texttt{conv2\_x}` stage names in Table 1. No separate appendix was built.
   This is a known deviation, not an over-claim; it would be tightened in round 2.
4. **`src/execution/*.py` and `imagenet_resnet34.yaml` not surfaced verbatim.** Their content
   is reflected in `alg:block` (forward pass) and the §3.4 recipe; the exact YAML/Python is
   appendix-substrate by `methodology-discipline` and was intentionally not pasted into the
   body.
5. **No biber.** Environment has `bibtex` but not `biber`; `natbib` + `plainnat` + `bibtex`
   used accordingly. Not a gap, just a toolchain note.
6. **`derived_from_table3` rendered as its own table** (`tab:shortcut`) in addition to the
   full Table 3 — the Book ships both, so both are surfaced (the derived subset adds the
   Δ-vs-plain-34 column the Book computed).

## 7. Compile evidence

- Command: `latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex` (TeX Live 2026,
  latexmk 4.83), log at `compile.log` / `main.log`.
- Final pass: **0 undefined references, 0 undefined citations, 0 `??` markers, 0 overfull
  hboxes** (one 27.77pt overfull in Table 1 was fixed via `\resizebox` in iteration 2).
- Output: `paper.pdf`, 13 pages, ~498 KB, all fonts embedded (`pdffonts` shows every font
  `emb=yes`).
- Iterations used: 3 (initial build → fix Table 1 overfull → add third figure), within the
  skill's ≤3 budget.

## 8. Round-1 conclusion

The Book→Paper compiler produced a compilable, submission-shaped 13-page manuscript in which
all 8 falsifiable claims are surfaced, all 9 evidence tables (8 raw + 1 derived) are rendered
with exact numbers, and no body sentence is ungrounded or over-claimed. The measured gaps are
(a) the four qualitative-only Book figures, handled by prose + three number-exact replacement
figures, and (b) the body/appendix substrate split not yet applied. Both are improvement
targets for a round-2 regeneration, not correctness failures.


