---
slug: imported-paper-skill-catalog
summary: Map imported claude_write paper-writing skill names onto Writer's local workflow — prefer local skills, treat external names as task categories.
layer: scheduling
tools:
version: 2
status: active
supersedes:
references: end-to-end-paper-workflow, paper-work-boundaries
provenance: human
---

# Skill — Imported Paper Skill Catalog

The source `claude_write/AGENTS.md` listed many project-local skills. Do not assume those external `.codex/skills` files exist inside a MinionsOS project. Prefer local Writer skills; otherwise treat the imported name as a task category and execute through Writer's normal tools, subagents, and EACN handoffs.

## When to invoke

When a user explicitly names one of the imported skill names listed below. Map it to the nearest local skill; if none exists, state the local workflow you will use and keep outputs under `branches/writer/paper/`.

## Structure

Imported categories, grouped:

- **Literature and search:** `arxiv`, `deepxiv`, `exa-search`, `research-lit`, `research-review`, `semantic-scholar`, `systematic-literature-review`.
- **Paper drafting:** `paper-write`, `paper-write-sci`, `paper-writer`, `paper-writing`, `ml-paper-writing`, `sciwrite`, `systems-paper-writing`, `vibe-paper-writing`.
- **Claims and evidence:** `analyze-results`, `citation-audit`, `paper-claim-audit`, `result-to-claim`, `check-review-alignment`.
- **Figures and tables:** `academic-plotting`, `figure-description`, `figure-spec`, `paper-figure`, `paper-illustration`, `mermaid-diagram`.
- **LaTeX and packaging:** `make-latex-model`, `paper-compile`, `overleaf-sync`, `package-submission`, `transfer-old-latex-to-new`.
- **Automation loops:** `auto-paper-improvement-loop`, `autoresearch`, `researchclaw`, `researchclaw-cn`.

## Procedure

1. **Translate the imported name to the nearest local skill** under `minions/roles/writer/skills/` first.
2. **If no local equivalent exists,** treat the name as a task category: name the local workflow you will use, cite the local skills it composes, and keep outputs under `branches/writer/paper/`.
3. **Do not import external skill files** from `claude_write` or other projects into MinionsOS. Writer's skill surface is the list at `minions/roles/writer/skills/`.

## Pitfalls

- Assuming external `.codex/skills` files are present. They are not.
- Creating a new local skill file to mirror every imported name. Many imported names are synonyms for the same local workflow.
- Drifting outputs outside `branches/writer/paper/` because the imported name suggested a different layout.
