---
slug: role-skill-design
summary: Open when adding or revising a MinionsOS role skill, or when a role makes the same mistake in 2+ sessions — author a small Markdown skill at the right ownership layer.
layer: logical
tools:
version: 2
status: active
supersedes:
references: feature-intake, project-automation-audit, dialectics
provenance: human
---

# Skill — Role Skill Design

Turn a recurring role procedure into a small Markdown skill under the correct `minions/roles/<role>/skills/` directory. Sharpen decisions; do not duplicate the role's SYSTEM prompt.

## When to invoke

- Adding a new role skill (typically by Gru, but Coder may add one when shipping new system-maintenance procedures, and any role may propose one for itself).
- Refactoring a one-off prompt into reusable MinionsOS procedure.
- A role makes the same coordination, evidence, or boundary mistake in 2 or more separate sessions.

## Structure

Each skill file is discovered at wake-up by `minions.lifecycle.skills.list_skills`. The manifest-level discipline (SSL four-section template + frontmatter) is documented in `minions/roles/common/SKILLS.md` and the blank is at `minions/roles/common/_skill_template.md` — copy that, do not reinvent the layout. Skill ownership goes where responsibility lives; if two roles participate, write the skill for the role that decides or executes, and mention the EACN handoff.

## Procedure

1. **Identify the recurring move.** Name the trigger, role, expected artifact, and failure mode the skill prevents.
2. **Choose the owner role.** Put the skill where responsibility lives. If two roles participate, write for the one that decides or executes; mention the EACN handoff.
3. **Copy the template.** `minions/roles/common/_skill_template.md` gives the frontmatter and four H2 sections (`When to invoke`, `Structure`, `Procedure`, `Pitfalls`). Follow `minions/roles/common/SKILLS.md` for frontmatter semantics.
4. **Respect boundaries.** Include allowed paths, forbidden tools, EACN visibility, and subagent constraints when the procedure risks overreach.
5. **Name it predictably.** Lowercase hyphenated filename, matching the frontmatter `slug`.
6. **Validate discovery.** Ensure the frontmatter `summary:` reads as a useful one-line capability statement — that is what `[Skills]` injects at wake-up.
7. **Update role prompt only when needed.** If a role has no skill guidance or a hard-coded operational list, add a minimal reference without restating the skill.
8. **Report** new or changed skill paths, owner roles, and any SYSTEM prompt reference updates.

## Pitfalls

- Copying agent-host plugin text directly instead of translating it to MinionsOS role authority.
- Creating broad "be better at X" advice with no trigger or output habit.
- Adding skills for rare one-off tasks.
- Forgetting that subagents do not automatically inherit role skills.
