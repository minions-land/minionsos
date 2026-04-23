# Skill — Academic Plotting

Standards for publication-quality figures in ML / NLP / CV venues: when to use matplotlib vs a diagram tool, and what "camera-ready" means for each.

## Core move

Pick the right tool for the figure type, apply venue-standard styling, highlight "our method" deliberately, and produce both vector (PDF) and raster (PNG, 300 DPI) outputs reproducibly from a checked-in script.

## Procedure

1. **Classify the figure.** Numerical axes (bars, lines, scatter, heatmap, violin) → matplotlib/seaborn. Boxes-and-arrows (architecture, pipeline, workflow, cascade) → a diagram tool (mermaid for quick, SVG renderer or AI image for formal). Rule of thumb: numbers → matplotlib; structure → diagram.
2. **Pick the chart type from data shape.** Time/step on x-axis → line. N methods × M benchmarks → grouped bar. Single ranking → horizontal bar. Two continuous vars → scatter. Square matrix → heatmap. Proportions → stacked bar (avoid pie in ML papers).
3. **Apply publication defaults.** Font family matching venue (Times/Computer Modern for most; sans-serif OK if venue allows). Axis label fontsize 9–10 pt. Tick labelsize 8 pt. Line width ≥ 1.5 pt. Marker size ≥ 5 pt. Figure size: single-column ~3.3" wide, full-width ~7" wide.
4. **Use colorblind-safe palettes.** Okabe-Ito `#E69F00 #56B4E9 #009E73 #F0E442 #0072B2 #D55E00 #CC79A7` is the safe default. Reserve one distinct accent for "our method."
5. **Keep plotting scripts checked in.** `workspace/paper/figures/gen_fig_<name>.py` reads from a concrete data file under `workspace/experiments/` or `artifacts/exp-{id}/`. No hardcoded numbers. Re-run must reproduce byte-identical output modulo font rendering.
6. **Export both formats.** `fig.savefig(path.pdf)` for LaTeX inclusion; `fig.savefig(path.png, dpi=300)` for slide/web reuse. Verify LaTeX can include the PDF without font warnings.

## When to invoke

- Before every new figure goes into `workspace/paper/figures/`.
- When polishing a figure Coder produced — improve readability without changing scientific meaning.
- Before camera-ready, audit every figure against this checklist.

## Pitfalls

- Auto-generated defaults (blue/orange/green) that aren't colorblind-safe.
- Hardcoding numbers into plotting scripts — breaks reproducibility and evidence trace.
- Over-decorating: gradients, 3D bars, drop shadows. Flat beats fancy.
- Tiny axis labels that are unreadable at column width.

## Output habit

Each figure ships as: `gen_fig_<name>.py` (script), `fig_<name>.pdf`, `fig_<name>.png`, and a one-line provenance note in the script docstring citing the source data file — so all figure claims trace back per root §9.
