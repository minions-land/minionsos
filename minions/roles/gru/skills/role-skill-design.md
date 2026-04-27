# Skill — Role Skill Design

Create or revise MinionsOS role skills that make role behavior more reliable.

## Core move

Turn a recurring role procedure into a small Markdown skill under the correct
`minions/roles/<role>/skills/` directory. Skills should sharpen decisions; they
should not duplicate the role's whole SYSTEM prompt.

## Procedure

1. **Identify the recurring move.** Name the trigger, role, expected artifact,
   and failure mode the skill prevents.
2. **Choose the owner role.** Put the skill where responsibility lives. If two
   roles participate, write the skill for the role that decides or executes the
   procedure and mention the EACN handoff.
3. **Keep the file procedural.** Use `Core move`, `Procedure`, `When to invoke`,
   `Pitfalls`, and `Output habit` unless the local role already uses a tighter
   pattern.
4. **Respect boundaries.** Include allowed paths, forbidden tools, EACN
   visibility, and subagent constraints when the procedure risks overreach.
5. **Name it predictably.** Use lowercase hyphenated filenames such as
   `citation-audit.md` or `simplify-changes.md`.
6. **Validate discovery.** Ensure the first paragraph after the H1 is a useful
   one-line summary because role wake-up messages extract it automatically.
7. **Update role prompt only when needed.** If a role has no skill guidance or a
   hard-coded operational list, add a minimal reference without restating the
   skill.

## When to invoke

- Adding a new role skill.
- Refactoring a one-off prompt into reusable MinionsOS procedure.
- A role repeatedly makes the same coordination, evidence, or boundary mistake.

## Pitfalls

- Copying agent-host plugin text directly instead of translating it to MinionsOS
  role authority.
- Creating broad "be better at X" advice with no trigger or output habit.
- Adding skills for rare one-off tasks.
- Forgetting that subagents do not automatically inherit role skills.

## Output habit

Report the new or changed skill paths, which role owns each, and whether any
SYSTEM prompt reference was updated.
