---
slug: visual-format-check
summary: Format-agnostic visual layout audit over rendered PDF page images. Detects column voids, edge overflow, trailing whitespace, column imbalance, float clustering, short lines via the mos_visual_* MCP tools. Pixels do not lie — log/source heuristics do.
layer: physical
tools: mos_visual_render, mos_visual_inspect, mos_visual_check
version: 1
status: active
references: reliable-file-io
provenance: human+agent
---

# Skill — Visual Format Check

Pixel-level layout audit. Source / log inspection misses what only the rendered page exposes: a 30%-tall vertical white channel inside a column, a figure leaking 8px past the column rule, a final page that is 60% blank. The MCP tools below render then inspect; the skill is the discipline around them.

## When to invoke

- After Expert compiles a paper PDF, before signing off a draft
- After Expert produces a figure / plot artifact and wants size and overflow vetted before bundling
- When Ethics audits a "the figure is clear" claim made elsewhere
- When an Expert spot-checks a visual artifact attached to an EACN message
- When a Reviewer aspect note flags layout (forwarded as evidence; do not re-execute mid-review)

## Tools

- `mos_visual_render(pdf_path, output_dir?, dpi=220)` — Poppler rasterize PDF → `page_NNN.png`. DPI 220 for full-page audit, 300+ for table or formula spot checks.
- `mos_visual_inspect(target_path, kind="auto"|"layout"|"figure", report_path?)` — run detectors on a PDF, single image, or a `page_*.png` directory. `auto` picks layout for paper-sized double-column pages, figure for everything else.
- `mos_visual_check(pdf_path, output_dir?, dpi, kind="layout"|"figure", report_path?)` — render plus inspect in one call; rendered pages stay on disk for targeted re-inspection.

End-to-end audit is `mos_visual_check`. Use the two-step path when reusing renders across multiple inspections or different DPIs.

## Procedure

1. **Pick the right surface.** Whole paper → `mos_visual_check(pdf, kind="layout")`. Single figure file → `mos_visual_inspect(image, kind="figure")`. Pre-rendered page directory → `mos_visual_inspect(dir, kind="auto")`.
2. **Persist the report.** Pass `report_path` so the JSON `DefectReport` lands under `branches/<role>/visual-reports/<artifact>-<round>.json`. Defects without a stored report are not citable evidence. Visual reports stay per-role; cross-role consumers reference the path through an EACN message rather than via `mos_publish_to_shared` (no `shared/visual/` subdir today).
3. **Read the report, not the image dump.** `summary` gives defect counts by id; `pages[i].defects` lists per-defect bbox + score. Only render pages back to disk for the IDs that fired.
4. **Triage by severity.** `column_void` and `edge_overflow` block sign-off. `column_imbalance` and `float_clustering` are warnings unless the gap exceeds the configured threshold. `trailing_whitespace` and `short_line` are advisory polish.
5. **Cite by defect_id + page + bbox** in any EACN message: `[evidence: visual-report#<id>@p<page>(<bbox>)]`. Vague claims ("the layout looks bad") fail Ethics's evidence ratio check.

## Pitfalls

- **Don't argue from logs.** A clean `pdflatex` log can sit next to a 30% column void; the detectors run on pixels for a reason.
- **DPI matters.** Below 150 DPI the column-void projection is noisy; above 350 DPI memory cost dominates with no detection gain.
- **Single-column papers fail the `auto` heuristic for column-void**; pass `kind="figure"` explicitly when inspecting a single-column draft, or `kind="layout"` to force layout-mode regardless.
- **Don't store rendered images in `branches/<role>/`.** Page PNGs are large and ephemeral; keep them under `state/` or the project tmp dir, only commit the JSON report.
- **`mos_visual_*` tools never edit the PDF or source.** Fixes go through the
  responsible Expert using the normal paper or figure workflow; this skill
  produces evidence, not patches.

## Required coverage (R-future-5 lessons-learned)

A bbox-overlap-only audit on `ax.texts` is **not sufficient**. R-future-5 saw a "0 defects" report on a figure that visibly had a global title crashing into panel A's subtitle and panel C items overflowing their boxes. The audit must inspect every text-bearing element class:

| Coverage row | Source | What it catches |
|---|---|---|
| 1. `ax.texts` | per-axes | in-panel annotations (the only thing simple audits check) |
| 2. `ax.title`, `ax.xaxis.label`, `ax.yaxis.label` | per-axes | titles + axis labels (often longer than expected) |
| 3. `ax.get_xticklabels()` + `ax.get_yticklabels()` | per-axes | tick labels (long compartment names cross neighboring panels) |
| 4. `fig.texts` | figure-level | global title/subtitle blocks (R-future-5 main miss; `fig.text(...)` does NOT show up in `ax.texts`) |
| 5. inter-panel collision | every text from panel A vs every other panel's `get_window_extent()` | text from one panel bleeding into another |
| 6. text-over-image | every text vs every `ax.images[*].get_window_extent()` | wet-lab raster covered by stray annotation |
| 7. log-axis tick auto-extension | check `ax.get_xticks()` after `ax.set_xscale('log')` | matplotlib quietly adds 10^N ticks past `xlim`; pin with `FixedLocator` |

A "clean" audit must show empty defect lists across **all seven rows**. Reporting clean on rows 1+2 alone is the failure mode that masked R-future-5.

For local mos-tool-equivalent development (no MCP server available), implement these checks via matplotlib introspection. Reference implementation: `minions/tools/visual_audit_reference.py` (generic detection functions extracted from a real figure audit). The `mos_visual_*` detectors implement the same coverage on rasterized pages via OpenCV.
