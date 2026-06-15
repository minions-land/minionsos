---
slug: test-coverage-review
summary: Assess whether recent code changes have enough fast behavioral coverage; prefer one focused behavior test over broad line-coverage chasing.
layer: logical
tools:
version: 2
status: active
supersedes:
references: feature-implementation
provenance: human
---

# Skill — Test Coverage Review

One focused behavior test beats chasing line coverage.

## When to invoke

- Before completing any change that alters a public function signature, state schema, or CLI output.
- When Gru or formal review asks whether the change is covered.
- After a repair loop exposes a missing regression test.

## Structure

Map changed behavior → existing tests → critical gaps → add tests in Expert-owned paths. Priority gap order: lifecycle transitions, persisted state, role boundaries, EACN payloads, config defaults, CLI behavior, dashboard read-only guarantees. Tests stay fast and isolated — no live external services, no dependency on existing runtime state. For agent-host subprocess paths, use the existing fake launcher patterns (`MINIONS_FAKE_CLAUDE=1` for Claude).

## Procedure

1. **Map changed behavior.** List the user-visible or role-visible behaviors the diff changes, including failure paths.
2. **Find existing tests.** Read nearby unit, smoke, or dashboard tests; note the project's local style.
3. **Identify critical gaps.** Prioritize lifecycle transitions, persisted state, role boundaries, EACN payloads, config defaults, CLI behavior, and dashboard read-only guarantees.
4. **Add tests when Expert owns the path.** Fast and isolated; do not depend on existing runtime state or live external services.
5. **Use fake orchestration where needed.** Existing fake launcher patterns: `MINIONS_FAKE_CLAUDE=1` for Claude.
6. **Record untested risk.** If a gap needs heavy execution or human setup, submit to the experiment queue or ask Gru through EACN rather than faking confidence.
7. **Report** covered behaviors, added or existing test paths, commands run, and the highest-risk untested behavior if any remains.

## Pitfalls

- Testing implementation details instead of observable behavior.
- Adding slow tests to the unit suite.
- Relying on `minions/state/projects.json` or local machine state.
- Ignoring negative paths because the happy path passed once.
