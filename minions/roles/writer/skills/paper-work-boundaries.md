---
slug: paper-work-boundaries
summary: Open when about to issue a paper-* Workflow agent — ten-slot boundary map plus required structured-return shape; Workflow agents do not auto-inherit Writer's state.
layer: scheduling
tools: Workflow
version: 3
status: active
supersedes:
references: end-to-end-paper-workflow, role-act-via-workflow
provenance: human
---

# Skill — Paper Work Boundaries

Boundaries to include in every Workflow agent prompt; Workflow agents
do not automatically inherit Writer's full state.

## When to invoke

Open whenever Writer is about to dispatch paper work as a Workflow
agent — including the orchestrated path through
`end-to-end-paper-workflow` and any one-off direct dispatch.
Detection signal: you are about to issue a Workflow whose agent writes
inside `branches/writer/paper/` and you need to decide which slot
owns it.

## Structure

All paper work stays under `branches/writer/paper/`. Template /
reference directories such as `template/` or `branches/writer/template/`
are **read-only**. Existing results are inputs; do not run new
experiments or invent missing evidence.

**Required structured return** for every paper Workflow agent — three
fields, total ≤ 5 KB per common §4:

- `Completed` — short summary of work done.
- `Files Changed` — list of paths touched (all under the slot's
  allowed scope).
- `Needs Main Thread Attention` — blockers, missing evidence, claims
  that need Writer's judgment.

Cross-slot rule: work that spans two slots (e.g. a results figure that
needs both numerical plotting and prose interpretation) does not give
two Workflow agents write access to the same file. Dispatch slot A
first (single-agent or pipeline-stage); pass A's output as
**read-only context** to slot B's agent; slot B writes the final
artifact.

## Procedure

Pick the slot that matches the dispatched work from the boundary map
below. The mapped Workflow-agent name, its allowed scope, and the
read-only constraints go into the Workflow spec verbatim, plus the
three required return fields and the §10.1 scratchpad fragment.

At the end of every Workflow, verify: each agent's `Files Changed`
entries fall within its slot's allowed paths. Any cross-slot write is
a boundary violation — treat it as a failed dispatch rather than a
completed one.

Boundary map — pick the one that matches the dispatched work:

| Workflow agent | Scope |
|---|---|
| `paper-evidence-analyst` | Organize method facts, result numbers, comparison targets, missing evidence, open questions. Writes evidence notes only — not sections, figures, or tables. |
| `paper-literature-citation-builder` | Collect credible references, build a literature matrix, citation map, bibliography, citation gaps. Does not draft paper sections. |
| `paper-frontmatter-writer` | Title, abstract, introduction, related work — after evidence and citations are stable. |
| `paper-methods-writer` | Proposed method, formulation, architecture / module description, algorithm, method-specific implementation details. |
| `paper-results-writer` | Datasets, baselines, metrics, experimental setup, main results, ablations, error analysis, result interpretation grounded in existing outputs. |
| `paper-closing-writer` | Conclusion, compact discussion, optional limitations — after method / results are stable. |
| `paper-figure-python` | Result-grounded Python figures, plotting scripts, exports, captions. Does not reinterpret result meaning. |
| `paper-table-tex` | Result-grounded TeX tables and helper scripts with layout-safe formatting. |
| `paper-template-integrator` | Inspect template references, create / update the editable working copy under `branches/writer/paper/`, integrate sections / assets / bibliography, compile, fix layout / citation errors. |
| `paper-qa-auditor` | Final consistency across claims, numbers, citations, structure, references, figures / tables, compiled PDF readiness. Defaults to a report, not large rewrites. |

## Pitfalls

- Letting a Workflow agent write outside its slot (e.g.
  `paper-figure-python` editing prose).
- Reusing `template/` for live edits instead of cloning into
  `branches/writer/paper/`.
- Workflow agents inventing missing evidence rather than reporting it
  under `Needs Main Thread Attention`.
- **Scratchpad escape.** Every Workflow spec MUST include the §10.1
  scratchpad fragment so the agent's `./.claude/scratchpad/` resolves
  under `$MINIONS_ROLE_BRANCH/.claude/scratchpad/`. Without it, the
  PreToolUse hook will block path-shaped writes — costing you a turn
  and an EACN response.
