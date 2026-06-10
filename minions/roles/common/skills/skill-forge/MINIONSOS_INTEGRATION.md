# skill-forge - MinionsOS Integration

**Location:** `minions/roles/common/skills/skill-forge/`
**Version:** 1.0.0
**Created:** 2026-05-21

## Purpose

`skill-forge` is the lifecycle infrastructure for MinionsOS skills. Its subject
is the skill itself, not the role using the skill. Any Role can encounter a weak
trigger, unclear procedure, or bad behavior; the same evolution path then
improves the skill artifact.

## Lifecycle

```text
Stage 0  Request triage and mode selection
Stage 1  Skill creation: research related skills and draft Role Skill markdown
Stage 2  Structural validation: frontmatter, sections, triggers, references
Stage 3  Behavioral validation: concrete probes or focused regression tests
Stage 4  Iterative revision against observed failures
Stage 5  Summary and trigger-boundary optimization
Stage 6  Repository admission and enactment note
```

Each stage makes the skill more mature. The process does not mutate the Role
system and does not rely on a single expert's intuition.

## Evolution Loop

```text
Need identified
  -> candidate skill drafted
  -> structural validation
  -> behavioral validation
  -> trigger optimization
  -> repository skill admitted to production
  -> production weakness observed
  -> Stage 4 or Stage 5 creates the next generation
```

## MinionsOS Use Cases

### New skill admission

A missing capability is identified, a candidate skill is drafted, and
`skill-forge` drives it through structural and behavioral gates before it joins
the common skill library.

### Existing skill evolution

A production skill shows weak trigger behavior, ambiguous procedure, or poor
task outcomes. `skill-forge` builds positive and negative probes, evaluates
alternatives, and admits the best next generation.

### Pre-production quality gate

A candidate skill waits outside the library until Stage 2 and Stage 3 show that
it is structurally valid and behaviorally useful.

## Tool Integration

`skill-forge` coordinates three tool families:

- repository search with `rg`,
- discovery validation with `tests/unit/test_skills_discovery.py`,
- Role Skill contract validation with
  `MANUAL/scripts/validate_skill_operability.py`,
- focused unit tests when a skill affects runtime prompts or tooling.

## Metrics

Structural metrics:

- frontmatter validity,
- summary quality,
- trigger alignment,
- step ordering,
- absence of forward references.

Behavioral metrics:

- pass rate,
- token efficiency,
- elapsed time,
- behavior class.

Trigger metrics:

- precision,
- recall,
- F1 score.

Every generation should leave enough metric history to compare it against the
previous generation.

## Relationship To Other Components

- **EACN:** admitted common skills become available to EACN-visible Roles.
- **Role system:** common skills serve all Roles; role-specific skills can use
  the same lifecycle when they need specialization.
- **Workflows:** production skills become reusable procedure parts, while
  `skill-forge` keeps their reliability measurable.

## Bundle Structure

```text
skill-forge/
├── SKILL.md                 # operational procedure
├── README.md                # architecture notes
├── REGISTRATION.md          # suggested registration entry
├── SUMMARY.md               # executive summary
├── TOOL_INVENTORY.md        # tool inventory
└── MINIONSOS_INTEGRATION.md # this integration note
```

## Next Work

Short term:

1. Run the full lifecycle on several existing skills to establish baselines.
2. Write complete eval sets for common failure modes.

Medium term:

1. Collect Stage 3 behavioral data across the skill library.
2. Run Stage 5 trigger optimization for high-traffic skills.
3. Add generation metadata for traceability.

Long term:

1. Automate the production weakness -> evolution trigger -> replacement loop.
2. Visualize skill quality over generations.
3. Support cross-project migration for mature skills.
4. Add version management and rollback conventions.
