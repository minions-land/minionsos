# Skill — End-to-End Paper Workflow

Run a complete evidence-grounded paper-writing pipeline from project inputs to a compiled PDF.

1. **Gather inputs first.** Read the project brief, `workspace/` evidence files, result tables/logs, existing figures, and any `template/` reference material. Do not write prose until the evidence inventory is clear.
2. **Structure facts before narrative.** If method details, numbers, comparisons, or missing-evidence questions are not already organized, delegate to `paper-evidence-analyst` and require a traceable evidence summary.
3. **Build citations early.** Delegate to `paper-literature-citation-builder` before drafting frontmatter or related work. Require a bibliography, literature matrix, citation map, and explicit citation gaps.
4. **Delegate by boundary.** Use the paper work boundary names from Writer's `SYSTEM.md` for frontmatter, method, results, closing, figures, tables, template integration, and QA. When spawning a subagent, include the relevant boundary, allowed paths, forbidden paths, evidence rules, and required final report sections in the prompt.
5. **Keep evidence fixed.** Use existing experiment outputs only. If evidence is missing, ask Expert, Experimenter, Coder, Gru, or the user through EACN instead of inventing or rerunning results.
6. **Integrate into `workspace/paper/`.** Treat `template/` as read-only, create or update the editable working copy under `workspace/paper/`, connect sections/figures/tables/bibliography, and compile.
7. **Finish with QA.** Require `paper-qa-auditor` to check claims, numbers, citations, references, structure, table/figure fit, and compiled PDF readiness before calling the paper complete.

Avoid stopping at section drafts when the user asked for a manuscript. Missing PDF, unresolved citations, unsupported claims, or a too-thin bibliography are blockers.
