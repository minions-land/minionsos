# skill-forge Registration

`skill-forge` is a MinionsOS repository Role Skill procedure. Gru invokes it by
reading:

```text
minions/roles/common/skills/skill-forge/SKILL.md
```

## Role Skill Contract

- `slug: skill-forge`
- `summary:` describes repository Skill lifecycle work.
- `tools:` is advisory procedure metadata.
- The admitted artifact is a markdown file under `minions/roles/**/skills`.

## Routing

| Proposal op | Gru action |
|---|---|
| `add` | Create one Role Skill file and validate discovery. |
| `revise` | Edit the target file, bump `version:`, and revalidate. |
| `merge` | Admit the combined skill before hiding source skills. |
| `split` | Admit both child skills before hiding the source skill. |
| `drop` | Remove only when accepted evidence confirms no unique coverage remains. |

## Validation

```bash
uv run pytest tests/unit/test_skills_discovery.py -q
python3 MANUAL/scripts/validate_skill_operability.py
```

No user-level Claude Skill installation is part of this registration path.
