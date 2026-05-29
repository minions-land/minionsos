---
slug: end-to-end-paper-workflow
summary: Open when the user asked for a manuscript (not just section drafts) — seven-phase pipeline from project inputs to compiled PDF, with hard blockers preventing premature "done".
layer: composite
tools:
version: 2
status: active
supersedes:
references: paper-work-boundaries, citation-audit, paper-compile, package-submission, apply-revisions, prepare-rebuttal
provenance: human
---

# Skill — End-to-End Paper Workflow

A complete evidence-grounded paper-writing pipeline. Stop only when there is a compiled PDF with claims, citations, and figures that all trace.

## When to invoke

- The user requested a manuscript (not just section drafts).
- A project has stable experimental results and a target venue.
- Re-running after a major revision that changes claims, results, or venue.

If evidence is missing, stop and ask Expert / Coder / Gru / user through EACN — do not invent or rerun results inside Writer.

## Structure

Seven phases: gather inputs → structure facts → build citations →
dispatch by boundary → keep evidence fixed → integrate under
`branches/writer/paper/` → QA. The pipeline runs as a single
`Workflow` with `phase` shape (one phase per stage, hard gate between
each). Workflow-agent boundaries are listed in `paper-work-boundaries`.
Existing experiment outputs are inputs only; `template/` is read-only;
the editable working copy lives under `branches/writer/paper/`.

Blockers that prevent calling a paper "done": missing PDF, unresolved
citations, unsupported claims, too-thin bibliography, structural
failures from QA.

## Procedure

1. **Gather inputs first.** Read the project brief,
   `branches/<role>/` evidence (primarily `branches/coder/` and
   `branches/coder/exp/`), result tables / logs, existing figures,
   and any `template/` reference material. Do not write prose until
   the evidence inventory is clear.
2. **Structure facts before narrative.** If method details, numbers,
   comparisons, or missing-evidence questions are not already
   organized, dispatch a `paper-evidence-analyst` Workflow agent and
   require a traceable evidence summary.
3. **Build citations early.** Dispatch a
   `paper-literature-citation-builder` Workflow agent before drafting
   frontmatter or related work. Require a bibliography, literature
   matrix, citation map, and explicit citation gaps.
4. **Dispatch by boundary** per `paper-work-boundaries`. Use a single
   `Workflow.phase()` covering frontmatter / method / results /
   closing / figures / tables / template-integration / QA. Each phase
   carries a hard precondition gate (no drafting without citations,
   no QA without compile). Parallel-drafting fan-out (multiple
   sections at once when evidence is stable) lives inside phase 4.
   Each Workflow-agent spec includes the relevant boundary, allowed
   paths, forbidden paths, evidence rules, the §10.1 scratchpad
   fragment, and the three required return fields.
5. **Keep evidence fixed.** Use existing experiment outputs only.
   Missing evidence → ask via EACN, never invent.
6. **Integrate into `branches/writer/paper/`.** Treat `template/` as
   read-only, create or update the editable working copy, connect
   sections / figures / tables / bibliography, compile.
7. **Finish with QA.** The `paper-qa-auditor` Workflow agent is the
   gating verifier of phase 7 — it must pass before the pipeline
   exits with a "done" structured return.

End-to-end Workflows MUST run with `run_in_background=true` per
common §4 — Gru's review traffic must never see a stale Writer.

## Pitfalls

- Stopping at section drafts when the user asked for a manuscript.
- Letting Workflow agents skip the required structured return fields
  (`Completed`, `Files Changed`, `Needs Main Thread Attention`).
- Running new experiments inside Writer.
- Treating `template/` as editable.
- Forgetting the §10.1 scratchpad fragment in the Workflow spec —
  the PreToolUse hook will block path-shaped writes inside the
  agent.
