# Skill — Imported Paper Skill Catalog

Map imported `claude_write` paper-writing skill names onto Writer's local workflow.

The source `claude_write/AGENTS.md` listed many project-local skills. Do not assume those external `.codex/skills` files exist inside a MinionsOS project. Prefer skills already present under `minions/roles/writer/skills/`; otherwise treat the imported name as a task category and execute through Writer's normal tools, subagents, and EACN handoffs.

Relevant imported categories:

- Literature and search: `arxiv`, `deepxiv`, `exa-search`, `research-lit`, `research-review`, `semantic-scholar`, `systematic-literature-review`.
- Paper drafting: `paper-write`, `paper-write-sci`, `paper-writer`, `paper-writing`, `ml-paper-writing`, `sciwrite`, `systems-paper-writing`, `vibe-paper-writing`.
- Claims and evidence: `analyze-results`, `citation-audit`, `paper-claim-audit`, `result-to-claim`, `check-review-alignment`.
- Figures and tables: `academic-plotting`, `figure-description`, `figure-spec`, `paper-figure`, `paper-illustration`, `mermaid-diagram`.
- LaTeX and packaging: `make-latex-model`, `paper-compile`, `overleaf-sync`, `package-submission`, `transfer-old-latex-to-new`.
- Automation loops: `auto-paper-improvement-loop`, `autoresearch`, `researchclaw`, `researchclaw-cn`.

When a user explicitly names one of these imported skill names, first look for an equivalent local Writer skill. If no local skill exists, state the nearest local workflow you will use and keep outputs under `workspace/paper/`.
