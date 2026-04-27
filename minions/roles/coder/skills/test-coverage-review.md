# Skill — Test Coverage Review

Assess whether recent code changes have enough fast behavioral coverage.

## Core move

Look for missing tests that would catch realistic regressions. Prefer one focused
behavior test over broad line-coverage chasing.

## Procedure

1. **Map changed behavior.** List the user-visible or role-visible behaviors the
   diff changes, including failure paths.
2. **Find existing tests.** Read nearby unit, smoke, or dashboard tests and note
   the project's local style.
3. **Identify critical gaps.** Prioritize lifecycle transitions, persisted state,
   role boundaries, EACN payloads, config defaults, CLI behavior, and dashboard
   read-only guarantees.
4. **Add tests when Coder owns the path.** Keep tests fast and isolated; do not
   depend on existing runtime state or live external services.
5. **Use fake orchestration where needed.** For Claude subprocess paths, prefer
   `MINIONS_FAKE_CLAUDE=1` and existing smoke patterns.
6. **Record untested risk.** If a gap needs heavy execution or human setup, ask
   Experimenter/Gru through EACN rather than faking confidence.

## When to invoke

- Before completing a feature, bug fix, or refactor with behavioral impact.
- When Reviewer or Gru asks whether the change is covered.
- After a repair loop exposes a missing regression test.

## Pitfalls

- Testing implementation details instead of observable behavior.
- Adding slow tests to the unit suite.
- Relying on `minions/state/projects.json` or local machine state.
- Ignoring negative paths because the happy path passed once.

## Output habit

Return covered behaviors, added or existing test paths, commands run, and the
highest-risk untested behavior if any remains.
