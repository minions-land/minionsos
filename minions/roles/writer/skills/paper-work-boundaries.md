# Skill — Paper Work Boundaries

Use these boundaries when Writer delegates focused paper work to subagents.

Include the relevant boundary text in the subagent prompt because subagents do not automatically inherit Writer's full state. All paper work stays under `workspace/paper/`. Template/reference directories such as `template/` or `workspace/template/` are read-only. Existing results are inputs; do not run new experiments or invent missing evidence.

Required final report sections for every delegated paper subagent:

1. `Completed`
2. `Files Changed`
3. `Needs Main Thread Attention`

Boundary map:

- `paper-evidence-analyst`: organize method facts, result numbers, comparison targets, missing evidence, and open questions. Writes evidence notes only, not sections, figures, or tables.
- `paper-literature-citation-builder`: collect credible references, build a literature matrix, citation map, bibliography, and citation gaps. Does not draft paper sections.
- `paper-frontmatter-writer`: draft title, abstract, introduction, and related work after evidence and citations are stable.
- `paper-methods-writer`: draft the proposed method, formulation, architecture/module description, algorithm, and method-specific implementation details.
- `paper-results-writer`: draft datasets, baselines, metrics, experimental setup, main results, ablations, error analysis, and result interpretation grounded in existing outputs.
- `paper-closing-writer`: draft conclusion, compact discussion, and optional limitations after method/results are stable.
- `paper-figure-python`: create result-grounded Python figures, plotting scripts, exports, and captions. Does not reinterpret result meaning.
- `paper-table-tex`: create result-grounded TeX tables and helper scripts with layout-safe formatting.
- `paper-template-integrator`: inspect template references, create/update the editable working copy under `workspace/paper/`, integrate sections/assets/bibliography, compile, and fix layout/citation errors.
- `paper-qa-auditor`: check final consistency across claims, numbers, citations, structure, references, figures/tables, and compiled PDF readiness. Defaults to a report, not large rewrites.
