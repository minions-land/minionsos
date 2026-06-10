# MinionsOS Markdown Asset Index

This file maps Markdown files to their runtime or documentation role. It exists
so Markdown assets are discoverable by purpose instead of living as unlabelled
prose files.

## Language Policy

All MinionsOS-owned Markdown descriptions and operational documentation are
English. The Chinese section of `README.md` is retained as the public bilingual
introduction. The `mcp-servers/eacn3/` subtree is protected and must not be
edited by this repository documentation policy; treat its Markdown as read-only
upstream content.

## Root Documentation

| Path | Role |
|---|---|
| `README.md` | Public overview. English is canonical; the Chinese section is the only allowed Chinese prose. |
| `AGENTS.md` | Repository instructions for coding agents working in this checkout. |
| `CLAUDE.md` | Claude-facing runtime and collaboration instructions. |
| `CHANGELOG.md` | Versioned project change history. |
| `ERRORS.md` | Error taxonomy and troubleshooting reference. |
| `STABILITY.md` | Stability and support-level notes. |
| `MODULE_PATH_INDEX.md` | Runtime module map after the modularization pass. |
| `MARKDOWN_INDEX.md` | This Markdown asset map and language policy. |
| `RUST_CLI.md` | Rust CLI documentation (usage, architecture, performance). |
| `RUST_IMPLEMENTATION.md` | Rust enhancement implementation report (Phase 1 CLI + Phase 2 daemon). |

## Agent Manual

`MANUAL/` is the retrieval-shaped manual for Gru and Role agents.

| Path | Role |
|---|---|
| `MANUAL/MANUAL.md` | Always-on entry document loaded by agents. |
| `MANUAL/README.md` | Human-facing explanation of the manual system. |
| `MANUAL/SCHEMA.md` | Frontmatter schema for manual pages. |
| `MANUAL/INDEX.json` | Machine-readable index generated from page frontmatter. |
| `MANUAL/domains/*.md` | Domain cards. |
| `MANUAL/tools/*.md` | Atomic MCP tool pages. |
| `MANUAL/pitfalls/*.md` | Known-failure pages grounded in project evidence. |

Regenerate the manual index with:

```bash
python3 MANUAL/scripts/build_index.py
python3 MANUAL/scripts/validate.py
```

## Role Prompts And Skills

Role prompt Markdown is runtime surface, not casual documentation.

| Path | Role |
|---|---|
| `minions/roles/SYSTEM.md` | Shared Role contract. |
| `minions/roles/{role}/SYSTEM.md` | Role-specific system prompt. |
| `minions/roles/common/SKILLS.md` | Human-facing skill library manual. |
| `minions/roles/common/SKILL_EVAL.md` | Skill evaluation guidance. |
| `minions/roles/common/SKILL_BEHAVIORAL_EVAL.md` | Behavioral skill evaluation guidance. |
| `minions/roles/common/_skill_template.md` | Template for new role skills. |
| `minions/roles/common/skills/*.md` | Shared procedural skills discovered by `minions.lifecycle.skills.list_skills`. |
| `minions/roles/{role}/skills/*.md` | Role-specific procedural skills discovered by `list_skills`. |
| `minions/roles/common/skills/*/` | Progressive-disclosure bundles loaded only when routed by a top-level skill. |
| `minions/domains/*.md` | Expert domain-pack assets. |
| `.claude/skills/*/SKILL.md` | Checkout-local Claude skills that are versioned with the repository. |

Skill discovery is intentionally non-recursive. If a bundle directory matters,
route to it from a top-level skill and document the bundle in that skill.

## Review Assets

`minions/review/` powers `mos_review_run`.

| Path | Role |
|---|---|
| `minions/review/SYSTEM.md` | Area-chair prompt for structured review rounds. |
| `minions/review/skills/*.md` | Procedural review skills. |
| `minions/review/personas/*.md` | Reviewer-instance personas. |
| `minions/review/templates/*.md` | Output templates consumed by the review runner. |

Keep these files aligned with `tests/unit/test_review_e2e_fake.py` and
`tests/unit/test_review_mcp.py` when changing review behavior.

## MCP Server Documentation

| Path | Role |
|---|---|
| `mcp-servers/README.md` | Registry for standalone MCP servers in this repository. |
| `mcp-servers/minionsos.md` | MinionsOS MCP server notes. |
| `mcp-servers/eacn3/` | Protected upstream EACN3 subtree; indexed here only as read-only external content. |

## Dashboard And TUI

| Path | Role |
|---|---|
| `minions-viz/REDESIGN.md` | Dashboard redesign notes. |
| `minions-tui/README.md` | TUI overview. |
| `minions-tui/DESIGN.md` | TUI design notes. |

## Tests And Generated State Notes

| Path | Role |
|---|---|
| `tests/smoke/README.md` | Smoke-test guidance. |
| `workflow-plugins/README.md` | Workflow plugin overview. |
| `workflow-plugins/*/domain.md` | Workflow plugin domain metadata. |
| `minions/state/codex-gru.AGENTS.md` | Generated/runtime agent instruction snapshot; do not use as canonical source. |

Generated project worktrees, logs, caches, and local runtime state are not
documentation surfaces and should not be indexed here.
