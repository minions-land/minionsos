# skill-forge — MinionsOS Role Skill Lifecycle

`skill-forge` is the repository procedure for changing MinionsOS Role Skills.
It is used after Ethics accepts a Knowledge-axis proposal and Gru needs to
create, revise, merge, split, or drop files under `minions/roles/**/skills`.

## Current Flow

```text
proposal in branches/main/notes/skill-proposals.md
  -> Ethics skill-audit verdict
  -> Gru reads skill-forge/SKILL.md
  -> repository Role Skill file changes
  -> validation
  -> enactment note in the proposal ledger
```

## Scope

- Source of truth: `minions/roles/common/skills/` and
  `minions/roles/<role>/skills/`.
- Registration signal: `slug:` plus `summary:` frontmatter.
- Discovery path: `minions.lifecycle.skills.list_skills(role)` injects
  `slug: summary` pairs into the Role wake-up `[Skills]` block.
- Validation: `tests/unit/test_skills_discovery.py` and
  `MANUAL/scripts/validate_skill_operability.py`.

## Bundle Structure

```text
skill-forge/
├── SKILL.md                 # operational procedure
├── README.md                # this overview
├── REGISTRATION.md          # repository registration note
├── SUMMARY.md               # executive summary
├── TOOL_INVENTORY.md        # validation and helper surfaces
└── MINIONSOS_INTEGRATION.md # integration note
```

The procedure never requires user-level Claude configuration. A delivered
MinionsOS checkout contains the Role Skill library it needs.
