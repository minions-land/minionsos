# skill-forge Tool Inventory

These are the repository-local tools and checks used by `skill-forge`.

## Search

```bash
rg -n "<slug|trigger|concept>" minions/roles/common/skills minions/roles/*/skills
```

Use this before adding, merging, splitting, or dropping a skill so coverage
changes are based on the current library.

## Discovery Validation

```bash
uv run pytest tests/unit/test_skills_discovery.py -q
```

Checks that `minions.lifecycle.skills.list_skills(role)` discovers direct
`*.md` files, hides `status: deprecated` / `status: merged`, and keeps nested
progressive-disclosure bundles out of the wake-up list.

## Prompt / Manual Validation

```bash
python3 MANUAL/scripts/validate_skill_operability.py
```

Checks that Role Skill files use repository metadata, Role-facing docs point to
`minions/roles/**/skills`, workflow-plugin sources render into project-local
bundles, and the Role wake-up prompt includes `[Skills]`.

## Broader Gates

Run these when the change touches shared runtime code, prompts, or generated
manual surfaces:

```bash
uv run pytest tests/unit -q
uv run ty check minions
uv run ruff check .
uv run ruff format --check .
python3 MANUAL/scripts/build_index.py
python3 MANUAL/scripts/validate.py
```

## Output Contract

`skill-forge` reports the changed paths, commands run, and final verdict in the
proposal ledger enactment block. It does not depend on user-level Claude
configuration.
