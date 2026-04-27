# Skill — Change Review

Review recent code changes for correctness, role-boundary fit, and project
conventions before reporting completion.

## Core move

Take a code-review stance on the diff Coder is about to hand off. Findings lead;
style notes matter only when they affect maintainability, contracts, or future
debuggability.

## Procedure

1. **Scope the diff.** Inspect staged and unstaged changes relevant to the task.
   Ignore unrelated user changes.
2. **Check behavior first.** Look for logic errors, state corruption, path
   mistakes, subprocess misuse, missing error propagation, and broken edge cases.
3. **Check MinionsOS boundaries.** Verify that Coder did not write role-owned
   artifacts, bypass EACN for role communication, run heavy experiments, or touch
   generated runtime state unnecessarily.
4. **Check configuration and persistence.** For lifecycle, state, and config
   changes, verify migration behavior, default values, and project isolation.
5. **Check tests.** Confirm changed behavior has a fast local test or a clear
   reason why a test is not practical.
6. **Decide action.** Fix high-confidence issues immediately if they are within
   scope. Defer or report low-confidence concerns instead of churning.

## When to invoke

- Before returning an EACN result after non-trivial implementation.
- Before asking Gru or the author to accept a code change.
- After a repair loop or feature implementation touches shared lifecycle, state,
  role, tool, or dashboard behavior.

## Pitfalls

- Reviewing the entire repository instead of the task diff.
- Reporting speculative issues without file/line evidence.
- Treating lint-only complaints as review findings unless they reflect a real
  project rule.
- Reverting user changes outside the task.

## Output habit

List findings first, ordered by severity, with file and line references. If no
issues are found, say so and name any remaining test gap or residual risk.
