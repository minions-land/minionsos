# skill-forge — Executive Summary

`skill-forge` is the MinionsOS procedure for maintaining Role Skills as
repository artifacts. It turns Ethics-accepted Knowledge-axis proposals into
validated changes under `minions/roles/**/skills`.

## What It Does

- Confirms the proposal is in the Role Skill scope.
- Checks overlap against the current library.
- Creates or edits markdown skill files with `slug:` / `summary:`
  frontmatter.
- Preserves lineage through `references:` and `supersedes:`.
- Runs discovery and operability validation.
- Records Gru enactment back into `branches/main/notes/skill-proposals.md`.

## Required Shape

```yaml
---
slug: lowercase-hyphen-stem
summary: One-line wake-up triage statement.
layer: scheduling | structural | logical | composite
tools: advisory tool names
version: 1
status: active
supersedes:
references:
provenance: human+agent
---
```

The Role Skill body uses:

```markdown
## When to invoke
## Structure
## Procedure
## Pitfalls
```

## Authority Split

- Ethics accepts or rejects proposals.
- Gru enacts accepted proposals.
- Roles consume only admitted repository files.

## Verification

```bash
uv run pytest tests/unit/test_skills_discovery.py -q
python3 MANUAL/scripts/validate_skill_operability.py
```

The delivered repository is the source of truth; user-level Claude
configuration is not required.
