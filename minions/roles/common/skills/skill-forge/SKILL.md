---
slug: skill-forge
summary: Create, revise, merge, split, or drop MinionsOS Role Skill files under minions/roles/**/skills after Ethics accepts a proposal.
layer: composite
tools: Read, Write, Edit, Bash, rg, uv
version: 2
status: active
supersedes:
references: role-skill-design, test-coverage-review, evidence-driven-proposal
provenance: human+agent
---

# Skill — Skill Forge

Maintain the MinionsOS Role Skill library as repository source. This procedure
does not install files into user-level Claude configuration. Every admitted
artifact lives under `minions/roles/common/skills/` or
`minions/roles/<role>/skills/`.

## When to invoke

- Gru receives an Ethics-accepted Knowledge-axis proposal from
  `branches/main/notes/skill-proposals.md`.
- A user asks to add, revise, merge, split, or drop a MinionsOS Role Skill.
- A Role finds a recurring failure pattern that should become a reusable
  repository procedure.

Skip this procedure for MCP tools, domain packs, role SYSTEM.md changes, and
workflow-plugin packaging. Those have separate contracts.

## Structure

Inputs:

- `op`: `add`, `revise`, `merge`, `split`, or `drop`.
- `target_skill_path` for revise/drop operations.
- `draft_skill_md` or source skill paths for add/merge/split operations.
- Evidence pointers from the accepted proposal.

Outputs:

- A repository markdown skill file with valid Role Skill frontmatter.
- Focused validation notes in the proposal enactment block.
- Tests or validator updates when the change affects discovery, prompts, or
  tooling.

Authority:

- Ethics accepts or rejects proposals.
- Gru applies accepted proposals and records enactment.
- Operating Roles consume only admitted repository files.

## Procedure

1. **Confirm scope.** Verify the proposal is Knowledge-axis and that the
   target path is inside `minions/roles/common/skills/` or
   `minions/roles/<role>/skills/`. Do not write user-level Claude
   configuration.

2. **Read current coverage.** Search the skill library for overlapping slugs,
   summaries, references, and body triggers:

   ```bash
   rg -n "<concept|slug|trigger>" minions/roles/common/skills minions/roles/*/skills
   ```

3. **Choose the destination.** Use `common/skills/` for cross-role procedure.
   Use a role-specific directory only when the procedure depends on that
   Role's authority, write scope, or recurring task type.

4. **Write Role Skill frontmatter.** The file must use this schema:

   ```yaml
   ---
   slug: lowercase-hyphen-stem
   summary: One-line wake-up triage statement.
   layer: scheduling | structural | logical | composite
   tools: comma-separated advisory tool names
   version: 1
   status: active
   supersedes:
   references:
   provenance: human | human+agent | ai-suggested | user-revised
   ---
   ```

   `slug:` must match the file stem. `summary:` is the Role wake-up signal.
   `tools:` is advisory procedure metadata; MCP access is still governed by
   `--allowed-tools` plus server-side authorization.

5. **Use the four-section body.** Keep the procedure short and executable:

   ```markdown
   # Skill — <Name>

   <One-line operational summary.>

   ## When to invoke
   ## Structure
   ## Procedure
   ## Pitfalls
   ```

6. **Apply the requested op.**

   | Op | Action |
   |---|---|
   | `add` | Create one new skill file. Prefer a narrow trigger over broad policy prose. |
   | `revise` | Edit the existing file, bump `version:`, and update `summary:` if trigger semantics changed. |
   | `merge` | Create the combined file, set `supersedes:` to source slugs, then mark source files `status: merged` only after the combined file validates. |
   | `split` | Create the child files first, then mark the source `status: merged` only after both children validate. |
   | `drop` | Remove only after the accepted proposal confirms no unique coverage remains; otherwise mark `status: deprecated` and leave references clear. |

7. **Validate repository behavior.**

   ```bash
   uv run pytest tests/unit/test_skills_discovery.py -q
   python3 MANUAL/scripts/validate_skill_operability.py
   ```

   If discovery, prompt injection, workflow-plugin mounting, or documentation
   contracts changed, also run the affected unit tests.

8. **Record enactment.** In `branches/main/notes/skill-proposals.md`, append:

   ```markdown
   ### enactment (by gru on YYYY-MM-DD)
   - status: enacted | superseded
   - paths_changed: [...]
   - validation: <commands and result>
   - notes: <one-line reason for final decision>
   ```

## Pitfalls

- Do not use `name:`, `description:`, or `allowed-tools:` in Role Skill
  frontmatter. Those are not the MinionsOS Role Skill schema.
- Do not require host-level personal Claude configuration; users receive the
  repository Role Skill library.
- Do not add a broad skill when a focused edit to an existing skill covers the
  failure.
- Do not admit a skill whose evidence points do not resolve.
- Do not mark source skills hidden before the replacement validates.
- Do not change MCP authorization, Role boundaries, or EACN behavior from this
  procedure. Route those through their own review surfaces.
