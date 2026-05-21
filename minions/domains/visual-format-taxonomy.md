# Domain Pack: Visual Format Taxonomy (visual-format-taxonomy)

You are an expert in document visual layout and typesetting quality. This pack
gives operational context for inspecting rendered page images and
classifying defects, independent of the source format (LaTeX, Word, HTML
print, slide deck export). Pair with the `visual-format-check` skill, which
exposes the rendering and detection MCP tools.

## Core scope

Visual layout audit of rendered documents (PDFs and figures) at the **pixel**
level — not the source level. Coverage:

- Per-page space-utilization defects (column voids, trailing whitespace,
  end-page balance).
- Page-edge integrity (text or float content overflowing the printable area
  or column rule).
- Inter-column / inter-page balance for two-column layouts.
- Figure / table placement clustering and spread.
- Line-level pathologies (very short or orphan / widow lines).
- Single-figure quality (edge bleed, cropping artifacts, oversized borders).

Out of scope: typographic correctness *content* (style, citation format,
language), structural correctness (heading levels, missing sections), and
semantic claims (whether the figure actually shows what the caption says).
Those belong to Writer / Ethics / Reviewer review surfaces, not the visual
detector.

## Canonical references

- Bringhurst, R. (2004). *The Elements of Typographic Style*. Hartley & Marks.
  Chapters 2–4 establish vertical rhythm and balance norms.
- Tschichold, J. (1991). *The Form of the Book*. Hartley & Marks. Page-balance
  and orphan / widow conventions.
- Hochuli, J. (2008). *Detail in Typography*. Hyphen Press. Line-end and
  column-edge treatment.
- ICML / NeurIPS / CVPR / ACL author kits — concrete two-column constraints
  that drive the column-void and column-imbalance heuristics.
- Adobe and Microsoft accessibility guides on margin / overflow tolerances.

## Defect categories (format-agnostic)

The MCP tool surface emits these `defect_id` values. Severity is *advisory*
in the report; the role decides whether each blocks sign-off.

| defect_id            | Family            | What it captures                                                | Block-by-default |
| -------------------- | ----------------- | --------------------------------------------------------------- | ---------------- |
| `column_void`        | Space utilization | Vertical white channel inside one column with content beside it | yes              |
| `trailing_whitespace`| Space utilization | Final page below threshold of inked area                        | no               |
| `column_imbalance`   | Space utilization | Two-column page with large left/right height gap                | warn only        |
| `edge_overflow`      | Edge integrity    | Ink crosses the margin / column rule by > N px                  | yes              |
| `float_clustering`   | Float placement   | 2+ floats stacked with no body text between them                | warn only        |
| `short_line`         | Line pathology    | Trailing partial line below threshold (orphan / widow proxy)    | no               |

Notes:

- Codes are **deliberately generic**. Do not reintroduce upstream
  vendor-specific codes (e.g., the LaTeX-only `A1`–`E3` taxonomy from PaperFit)
  into MinionsOS artifacts — the same engine will run against Word exports,
  HTML print, and slide PDFs.
- `kind="layout"` activates the full set; `kind="figure"` activates only
  `edge_overflow`, since a single figure has no columns or page edges to
  balance.

## Common methods (how the detectors decide)

- **Column void:** binarize page → vertical projection of inked rows per
  column → find runs ≥ ~30% of column height where projection ≈ 0 *and*
  the *other* column has a non-trivial projection in the same row range.
- **Trailing whitespace:** total inked-area ratio of the bottom N rows of
  the last page; threshold-based.
- **Edge overflow:** dilate ink mask, intersect with margin / column-rule
  band (computed from page geometry, not source). Any intersection > N px
  fires.
- **Column imbalance:** vertical centroid of ink per column; flag if the
  difference exceeds a fraction of page height.
- **Float clustering:** detect float bounding boxes by run-length on column
  background; fire when 2+ contiguous floats share a column with < N body
  rows between them.
- **Short line:** locate text rows by horizontal projection; trailing row of
  a paragraph block below width threshold fires `short_line`.
- **Auto kind selection:** decided by aspect ratio + double-column heuristic
  (large central low-ink corridor running ≥ 70% of page height).

All detectors are deterministic OpenCV operations on the rasterized page;
no learned model. Replicable across renders at the same DPI.

## Typical pitfalls

- **Reporting log-clean as visually-clean.** A successful compile with no
  `Overfull \hbox` says nothing about a 30%-tall column void; the engine
  exists to catch exactly that mismatch.
- **DPI drift.** A defect that fires at 220 DPI may not fire at 144 DPI
  (projection noise floor changes). Always pin DPI in the persisted report
  so re-runs are comparable.
- **Treating warnings as blockers.** `column_imbalance` on the *last* page of
  a two-column paper is normal. The role applies severity policy on top of
  the raw defect list.
- **Re-rendering instead of reusing.** When iterating, render once with
  `mos_visual_render`, then run multiple `mos_visual_inspect` calls with
  different `kind` values — re-rendering the same PDF wastes ~10 s per page.
- **Single-column auto-detection.** A single-column draft will trip the
  column-void detector if `kind="auto"` mis-classifies it. Pass `kind`
  explicitly when in doubt.
- **Cross-format leakage.** Do not assume a fix applies cross-format. A
  LaTeX `\looseness=-1` will not change a Word export; the *defect* is
  format-agnostic, the *fix* is not.

## Useful toolchains

- `pdf2image` + Poppler (`pdftoppm`) for rasterization. Required for
  `mos_visual_render`.
- `opencv-python-headless` for projection / morphology / margin detection.
- `numpy` / `Pillow` for array glue and image-format conversion.
- `pdfplumber` or `PyMuPDF` (alternative renderers; not currently wired in).

## Evaluation norms

- **Defect rate per artifact:** count of fired defects / page count.
- **Severity-weighted score:** blocking defects × W_block + warning defects ×
  W_warn (W_block = 3, W_warn = 1 by current convention).
- **Round-over-round delta:** rate at round N vs. round N-1; the loop should
  monotonically decrease blocking defects.
- **False-positive sampling:** when iterating thresholds, hand-audit ≥ 10
  pages per defect_id before tightening — formats vary.
- **Report storage:** persist the structured `DefectReport` JSON, not page
  PNGs, into committed branches (PNGs go under `state/` or tmp). The JSON
  is the citable evidence; pages are reproducible from the source PDF.
