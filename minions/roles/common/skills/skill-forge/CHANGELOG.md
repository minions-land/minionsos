# MinionsOS Skill Evolution System - Changelog

**Version:** 1.0.0
**Released:** 2026-05-21
**Type:** New core capability: skill lifecycle management

## Added

### `skill-forge`

**Location:** `minions/roles/common/skills/skill-forge/`

`skill-forge` makes every skill a lifecycle-managed artifact rather than a
static prompt file. It drives a skill through creation, structural validation,
behavioral validation, iterative optimization, trigger-description tuning, and
packaging.

Lifecycle stages:

1. Stage 0: understand the request and choose the mode.
2. Stage 1: create the skill, study related skills, draft `SKILL.md`, and write
   eval cases.
3. Stage 2: validate structure, frontmatter, and trigger phrasing.
4. Stage 3: run behavioral validation through A/B tests or benchmark evals.
5. Stage 4: optimize through eval-set hill climbing.
6. Stage 5: tune the description against positive and negative trigger probes.
7. Stage 6: package the skill for distribution.

Bundle files:

- `SKILL.md` - the executable procedure.
- `README.md` - architecture notes.
- `REGISTRATION.md` - suggested Claude registration entry and diagrams.
- `SUMMARY.md` - executive summary.
- `TOOL_INVENTORY.md` - tool inventory.
- `MINIONSOS_INTEGRATION.md` - MinionsOS integration notes.

### `json-format`

**Location:** `minions/roles/common/skills/json-format/`

The first example skill for the lifecycle. It exercises Stage 1 and Stage 2
with `quick_validate.py` and `skill-edit`, demonstrating that a rough draft can
be brought to structurally valid form quickly.

## Why It Matters

Before `skill-forge`, skills tended to be handwritten, lightly tested, and then
left static. That made quality uneven, trigger accuracy hard to measure, and
library-wide improvement difficult.

With `skill-forge`, every skill can be:

- created from a measurable need,
- validated before production use,
- scored with repeatable metrics,
- evolved when trigger behavior or task behavior is weak,
- replaced with a better generation while preserving lineage.

## Metrics

Structural metrics:

- valid frontmatter,
- concise description,
- trigger phrases aligned with description,
- ordered procedure,
- no forward references.

Behavioral metrics:

- eval pass rate,
- token efficiency against baseline,
- runtime against baseline,
- behavior class: prevents failure, calibrates, matches baseline, or overreaches.

Trigger metrics:

- precision,
- recall,
- F1 score, with mature skills targeting F1 greater than 0.9.

## File Changes

New files:

```text
minions/roles/common/skills/skill-forge/
├── SKILL.md
├── README.md
├── REGISTRATION.md
├── SUMMARY.md
├── TOOL_INVENTORY.md
└── MINIONSOS_INTEGRATION.md

minions/roles/common/skills/json-format/
└── SKILL.md
```

## Compatibility

- Compatible with the existing MinionsOS skill library.
- Does not change EACN protocol behavior.
- Does not change the Role system.
- Adds lifecycle infrastructure incrementally.

## Status

`skill-forge`:

- `quick_validate.py` passed.
- `skill-edit` deep structural check passed.
- Stage logic documented.
- Stage 3 behavioral validation remains to be run on a broader candidate set.
- Stage 5 description optimization remains to be run on a broader candidate set.

`json-format`:

- `quick_validate.py` passed.
- `skill-edit` deep structural check passed.
- Broader in-use validation remains pending.

Core principle: a skill is a continuously evolving lifecycle artifact, not a
one-off static tool.
