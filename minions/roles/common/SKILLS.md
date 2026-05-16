# Skill management — methodology and operations

The `minions/roles/common/skills/` and `minions/roles/{role}/skills/` directories hold procedural skill files, discovered at Role startup by `minions.lifecycle.skills.list_skills` and surfaced to the Role as a `[Skills]` block in its initial system prompt. This document is the human-facing operating manual for that library: what a skill is, how skills compose, and how to add / query / modify / delete / merge one safely.

Keep it short. If this file grows beyond a page, the methodology has drifted.

## What a skill is

A single `.md` file with optional YAML frontmatter. One file, one skill. A skill is a reusable reasoning or procedure discipline — cross-domain, ≤100 lines, written for a language model to read. Domain knowledge belongs in `minions/domains/`, not here.

Every skill carries a **one-line summary** (≤200 chars) that is the only evidence the `[Skills]` block injects at wake-up. The rest of the file is loaded lazily, only when the Role decides it needs the detail.

## The SSL four-section template

Each skill's body has four H2 sections, mapping to the three retrieval questions plus a failure surface:

```markdown
---
<YAML frontmatter — see below>
---

# Skill — <Name>

<One-line summary; ≤100 chars. If no frontmatter `summary:` is set, this line is extracted instead.>

## When to invoke   — scheduling: triggers, preconditions, inputs/outputs
## Structure        — structural: phases, scene graph, which other skills compose
## Procedure        — logical: concrete tools, signatures, side effects, resources touched
## Pitfalls         — logical: failure modes, forbidden moves, common mistakes
```

An agent deciding "should I use this skill?" reads the frontmatter summary and `## When to invoke`. An agent planning reads `## Structure`. An agent executing reads `## Procedure` and `## Pitfalls`. The separation is what keeps context cost proportional to decision depth.

A ready-to-copy blank is at `minions/roles/common/_skill_template.md`.

## Frontmatter fields

Frontmatter is optional but recommended for every new skill. Unknown keys are silently ignored. Flat `key: value` only — no nested YAML.

| Key | Type | Purpose |
|---|---|---|
| `slug` | string | Canonical identifier; must match the file stem. |
| `summary` | string | One-line capability statement (≤200 chars); overrides body-derived summary. |
| `layer` | `scheduling` / `structural` / `logical` / `composite` | Which retrieval question this skill primarily answers. Routing skills are `scheduling`; FSM references are `structural`; per-tool procedures are `logical`; multi-layer skills are `composite`. |
| `tools` | comma list | MCP or lifecycle tools this skill governs. `[]` or omitted when the skill is pure procedure. |
| `version` | integer | Bumped on every `MODIFY`. Starts at `1`. |
| `status` | `active` / `deprecated` / `merged` | `active` is visible. `deprecated` and `merged` are hidden from `list_skills()` but remain on disk during a transition window. |
| `supersedes` | comma list of slugs | Skills this one replaces; set when merging or evolving. |
| `references` | comma list of slugs | Skills this one links to inside its body. Lets future maintainers detect dangling references before deletion. |
| `provenance` | `human` / `ai-suggested` / `user-revised` | Who wrote or last revised this skill, borrowed from ARA's provenance tag convention. |

Example minimal frontmatter:

```yaml
---
slug: bounded-repair-loop
summary: Fix a failing test in bounded iterations or stop and escalate.
layer: logical
tools:
version: 1
status: active
provenance: human
---
```

## The five verbs — how to maintain the library

Operations are plain filesystem operations. No registry, no build step, no service restart. `list_skills()` rediscovers on every Role wake-up.

### ADD — create a new skill

1. Pick the right directory. Cross-role reasoning → `common/skills/`. Role-specific procedure → `{role}/skills/`.
2. Choose a lowercase hyphen-separated slug. Keep it short and verb- or noun-led (`bounded-repair-loop`, `triage-request`).
3. Copy `minions/roles/common/_skill_template.md` to `{slug}.md`. Fill frontmatter and the four H2 sections.
4. Run `uv run pytest tests/unit/test_skills_discovery.py` to sanity-check frontmatter parsing.

That is the entire ADD operation. The next Role wake-up picks it up.

### QUERY — find and load skills

Roles query automatically: `list_skills()` injects `slug: summary` pairs at wake-up, and the Role `Read`s the file when it decides detail is needed. Humans can list what the library currently ships with:

```bash
ls minions/roles/common/skills/ minions/roles/*/skills/
```

For summaries without opening files, run a Python one-liner against `list_skills`, or grep the frontmatter `summary:` fields.

### MODIFY — edit an existing skill

1. Edit the file in place.
2. Bump `version:` in the frontmatter.
3. If the change alters `## When to invoke` semantics, update the `summary:` too — it is the primary triage signal.
4. If the skill now delegates to a new peer skill, add it to `references:` so future DELETE operations can detect the link.

The Role picks up the edit on its next wake-up. No restart.

### DELETE — retire a skill safely

Do not delete the file on day one. The safe sequence:

1. Flip `status: active` to `status: deprecated`. The file stays on disk; `list_skills()` will hide it from this wake-up onward.
2. Grep the rest of the library for `references:` entries or body mentions of the slug. Update any that point here.
3. After one full release cycle (or after a Gru-led sweep confirming no references remain), remove the file with `rm`.

This two-step retirement matches the lifecycle survey's "skill library is software, the same arithmetic applies" principle. Instant deletion is reserved for skills that were never referenced.

### MERGE / EVOLVE — combine, specialise, or fork

**MERGE** (two skills collapse into one):

1. Write the combined skill as a new file. In its frontmatter, set `supersedes: [a, b]`.
2. Mark the two originals `status: merged`. They are now hidden but still on disk for reference.
3. Grep for callers; point them at the new slug.
4. Retire the two originals using the DELETE flow above.

**EVOLVE** (one skill gains a role- or context-specific variant):

1. Keep the base skill in `common/skills/`.
2. Create the variant in the more specific directory (e.g. `writer/skills/`) with `supersedes:` set to the base slug. This documents the lineage without forking — the base remains authoritative for everyone else, while the variant specialises it for one consumer.
3. The variant does not need to copy the base's body; it can redirect to the base in `## Structure` and only override the sections that differ.

Both flows treat the skill library as an ecology rather than an archive: lineage is preserved, duplication is explicit, and nothing is silently lost.

## Token budget

The `[Skills]` block injected per wake-up is roughly `slug + ": " + summary + "\n"` per skill. With ~60 skills that is ≈1200 tokens per wake-up, comparable to a short system prompt. This is the ceiling; the body of any given skill is only loaded when the Role opens it. Keep summaries tight — every character multiplies across all future wake-ups.

## Further reading

Skill management here draws on three 2026 papers:

- **SSL** (Peking University, April 2026) — the four-section structural / scheduling / logical split.
- **ARA** (MIT / Michigan / Stanford, April 2026) — `provenance` and `supersedes` conventions for lineage.
- **SkillOS** (UIUC / Google, May 2026) — the lifecycle view: ADD / QUERY / MODIFY / DELETE / EVOLVE as first-class library verbs.

A full walkthrough is in `/Users/mjm/Skill/research-report.html`.
