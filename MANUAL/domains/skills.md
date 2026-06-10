---
id: domain-skills
kind: domain
domain: skills
auth: ['*']
source: minions/lifecycle/skills.py:1
since: stable
keywords: [skills, role-skills, workflow-plugin, skill-forge]
related: [mos_list_workflow_plugins, mos_spawn_expert]
status: stable
---

# Domain: Skills

MinionsOS Role skills are repository-shipped markdown procedures. Workflow
plugins may also mount project-local procedure bundles for the spawned Expert.
Host-level personal Claude configuration is outside the MinionsOS delivery
contract.

## Surfaces

| Surface | Location | How a Role uses it |
|---|---|---|
| MinionsOS Role skills | `minions/roles/common/skills/*.md`, `minions/roles/<role>/skills/*.md` | Read the markdown file directly after seeing its `slug: summary` in `[Skills]` |
| Workflow-plugin skills | `workflow-plugins/<slug>/skills/*.md` | Spawned Expert receives project-local `.claude/skills/workflow-plugin-<slug>-<skill>/SKILL.md` bundles inside its branch workspace |

## Metadata contract

| File type | Required registration metadata |
|---|---|
| Role skill markdown | `slug:` matches file stem; `summary:` is the wake-up triage line |
| Workflow-plugin source | Plain markdown is enough; MinionsOS renders project-local `name:` and `description:` at spawn |

`tools:` in a Role skill is advisory procedure metadata. Tool access is
controlled by `--allowed-tools` plus MCP server-side authorization.

## Operational checks

```bash
uv run pytest tests/unit/test_skills_discovery.py
uv run pytest tests/unit/test_agent_host.py -q
python3 MANUAL/scripts/validate_skill_operability.py
```

Use `minions/roles/common/SKILLS.md` for the authoring contract and
`workflow-plugins/README.md` for plugin packaging.
