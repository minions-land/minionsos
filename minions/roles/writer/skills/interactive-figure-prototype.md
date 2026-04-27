# Skill — Interactive Figure Prototype

Prototype paper figures with a local interactive HTML explorer before committing
to a static plot.

## Core move

Use a small playground to explore encodings, layout, filters, labels, and
caption framing when a figure has many visual degrees of freedom. The final
submission still needs static, reproducible figure assets.

## Procedure

1. **Name the figure decision.** Identify what is uncertain: grouping, metric
   selection, color, ordering, annotation, subplot layout, or narrative emphasis.
2. **Locate the evidence.** Use existing experiment outputs or Coder-produced
   figures only. Do not invent values or reinterpret results beyond Expert's
   evidence.
3. **Create a prototype path.** Write the explorer under
   `workspace/paper/figures/prototypes/<slug>.html`.
4. **Expose useful controls.** Let the user or Writer toggle encodings, labels,
   metric views, or caption variants. Keep controls tied to real data.
5. **Extract the static decision.** Once the layout is chosen, update the static
   plotting spec or ask Coder to produce the final figure asset.
6. **Preserve provenance.** Record the data source, script path, and any chosen
   visual settings in the figure notes or caption draft.

## When to invoke

- A figure is important but the best static presentation is unclear.
- Reviewer or Expert asks for clearer visualization of an existing result.
- A dashboard-like explorer would help choose one final paper figure.

## Pitfalls

- Treating an interactive prototype as a submission artifact.
- Creating visual impressions not supported by the underlying data.
- Making the figure prettier while changing scientific meaning.
- Spending prototype time on routine plots that already have a clear spec.

## Output habit

Return the prototype path, data provenance, chosen static figure direction, and
any Coder handoff needed for final plotting.
