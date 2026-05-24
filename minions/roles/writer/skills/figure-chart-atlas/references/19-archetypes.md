# 19 Archetypes — full reference

Provenance: distilled from awesome-writing-prompts "实验绘图推荐" prompt (FigureDraw2 reviewer_readiness leader 2.29) + nature-figure chart-atlas + figures4papers 11 demos.

For each archetype: when to use, when NOT, the implementation route, the typical pitfall.

## Family A — Numerical / performance comparison

### 1. Grouped vertical bar
- **When**: N methods × M benchmarks; M ≤ 6; method labels short.
- **When NOT**: M > 6 (use horizontal bar) or labels long.
- **Route**: matplotlib `ax.bar` with grouped offsets. See `figure-aesthetic-exemplars/ml-paper-idioms.md` §Ablation grouped-bar.
- **Pitfall**: y-axis from 0 when all values are 60–80 — wastes 60% of the panel.

### 2. Horizontal bar
- **When**: method labels long, OR > 6 methods to compare on one metric.
- **When NOT**: comparing across multiple metrics (use grouped-bar instead).
- **Route**: matplotlib `ax.barh`.
- **Pitfall**: not sorting by value — eye should walk the order.

### 3. Pareto frontier
- **When**: showing trade-off between two competing axes (accuracy vs latency, accuracy vs params).
- **When NOT**: only 1 axis matters (use bar).
- **Route**: scatter with frontier line drawn through the dominating points.
- **Pitfall**: not annotating which point is yours / which is best on each axis.

### 4. Radar (spider)
- **When**: ≥ 4 axes of comprehensive ability comparison; want to show "no weak axis".
- **When NOT**: < 4 axes (use grouped bar). Or values on different scales without normalisation.
- **Route**: matplotlib `polar` projection.
- **Pitfall**: 3 axes (collapses to triangle, hard to read). Or unnormalised axes (one axis dominates the shape).

### 5. Stacked bar
- **When**: composition / proportion of a whole across N conditions; total is meaningful.
- **When NOT**: components are not naturally part-of-a-whole. Or too many components (≥ 6 colors becomes unreadable).
- **Route**: matplotlib `ax.bar(..., bottom=cumulative)` repeated per stack layer.
- **Pitfall**: legend in alphabetical order — should be in the order layers stack.

## Family B — Trend / convergence

### 6. Line with error band
- **When**: training step / time / epoch on x; want to show convergence + variance.
- **When NOT**: only 1 seed (no variance to band).
- **Route**: `ax.plot` + `ax.fill_between`. See `ml-paper-idioms.md`.
- **Pitfall**: alpha > 0.25 on the band — overwhelms the mean line.

### 7. Zoomed inset
- **When**: many curves converge near the end and the gap is small but meaningful.
- **When NOT**: one curve is clearly dominant — the inset adds clutter.
- **Route**: `mpl_toolkits.axes_grid1.inset_locator.inset_axes`.
- **Pitfall**: inset overlapping legend or data; inset axis labels too small to read.

### 8. Scatter with fit
- **When**: show empirical relationship + the fitted law (R², slope).
- **When NOT**: data is categorical (use bar).
- **Route**: `ax.scatter` + `np.polyfit` + `ax.plot`.
- **Pitfall**: not annotating the R² and slope in the figure; over-saturating the data points (high alpha).

## Family C — Classifier / matrix

### 9. ROC curve
- **When**: binary classifier with reasonably balanced classes.
- **When NOT**: severe class imbalance (use PRC). Or multi-class (use per-class one-vs-rest panels).
- **Route**: `sklearn.metrics.roc_curve`.
- **Pitfall**: AUROC only in side table, not in legend.

### 10. Precision-Recall curve
- **When**: binary classifier with severe positive imbalance (positive rate < 5%).
- **When NOT**: balanced classes — ROC is the standard there.
- **Route**: `sklearn.metrics.precision_recall_curve`.
- **Pitfall**: missing prevalence baseline (a horizontal dashed line at the positive rate).

### 11. Heatmap
- **When**: matrix-shaped data — confusion matrix, similarity, multi-method × multi-task scores.
- **When NOT**: < 5 × 5 cells (use grouped bar). Or unrelated row/column orderings.
- **Route**: `ax.imshow` or `seaborn.heatmap`. Use `TwoSlopeNorm` for diverging signals (z-score, log-fold-change).
- **Pitfall**: rainbow colormap (`jet`). Use perceptually uniform — `viridis`, `RdBu_r` for diverging.

### 12. Scatter vs ground truth
- **When**: predicted vs actual; want to show calibration.
- **When NOT**: only summary metrics (R², MAE) suffice.
- **Route**: `ax.scatter` + diagonal `y = x` reference line.
- **Pitfall**: missing the diagonal reference; axes not square (`set_aspect('equal')`).

### 13. Bubble
- **When**: scatter where a third variable (params, cost) is shown by bubble size.
- **When NOT**: third variable is categorical (use color/marker shape).
- **Route**: `ax.scatter(s=...)`.
- **Pitfall**: bubble size linear in value (visually nonlinear) — should be `s ∝ value` for area, but readers see diameter; pick `s ∝ sqrt(value)` so visual area is linear.

## Family D — Distribution / structure

### 14. Violin
- **When**: comparing distributions across ≥ 2 conditions; want to show shape (bimodality).
- **When NOT**: < 30 samples per condition (violin's KDE is unreliable). Use box.
- **Route**: `seaborn.violinplot` or `ax.violinplot`.
- **Pitfall**: violin without inner box / median bar — readers can't find the central tendency.

### 15. Box plot
- **When**: distribution comparison, small samples, want quartiles + outliers.
- **When NOT**: distribution shape matters (use violin).
- **Route**: `ax.boxplot`.
- **Pitfall**: not jittering the underlying points alongside (loss of n information).

### 16. Ridgeline
- **When**: many groups (≥ 5) of distributions; want to show population-level shape change.
- **When NOT**: ≤ 3 groups (use overlay or violin).
- **Route**: matplotlib stacked KDE plots with vertical offset.
- **Pitfall**: too much overlap obscuring tail behavior; pick offset so curves overlap ≤ 30%.

### 17. Pie / donut (ML papers: avoid)
- **When**: ≤ 4 slices with large size differences AND total-as-100% is the message.
- **When NOT**: ML / NeurIPS / Cell papers — almost never. Use stacked bar.
- **Route**: `ax.pie`.
- **Pitfall**: 5+ slices, similar-sized slices (eye can't compare angles); 3D pie (forbidden).

### 18. Sankey / flow
- **When**: data prep flow, cohort flow, energy/material flow with magnitudes.
- **When NOT**: simple A→B without volume meaning (use figure-spec arrow).
- **Route**: [[figure-spec]] archetype B.
- **Pitfall**: per-link colors instead of source-color consistency. See figure-spec.md §Sankey.

### 19. Network graph
- **When**: nodes + edges with structural meaning; community / cluster identifiable.
- **When NOT**: > 100 nodes (becomes hairball — see network-graph-tuning.md for rescue).
- **Route**: `networkx` + matplotlib.
- **Pitfall**: random_layout (changes per run); constant node_size (collapses hierarchy).

### Forest plot (meta-analysis)
- **When**: aggregating point estimates with CIs across studies/cohorts.
- **When NOT**: single point estimate (use error bar).
- **Route**: matplotlib `errorbar` horizontal + diamond for pooled.
- **Pitfall**: missing the no-effect vertical reference (at 0 or at 1 depending on log-scale).

### Volcano plot
- **When**: differential expression / multiple-comparison highlight; x = effect size, y = -log10(p).
- **When NOT**: < 100 points or no need for significance threshold.
- **Route**: matplotlib scatter, color by 3 thresholds (down / non-sig / up).
- **Pitfall**: not annotating top hits; not drawing threshold lines (vertical at ±|FC|, horizontal at -log10(α)).

## Family E — Composite

### Dual-axis time series
- See `ml-paper-idioms.md` §Dual-axis. Use only when units genuinely differ.

### Bar + line composite
- **When**: background quantity (sample count) + foreground quantity (method accuracy) on long-tail.
- **Pitfall**: the two axes mean different things — must be color-coupled.

### Faceted grid
- **When**: too many comparison dimensions for one panel (e.g., method × dataset × seed × metric).
- **Route**: `seaborn.FacetGrid` or `subplots(N, M)`.
- **Pitfall**: not sharing axes — readers can't compare across facets.
