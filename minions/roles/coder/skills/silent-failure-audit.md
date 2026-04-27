# Skill — Silent Failure Audit

Find places where errors are swallowed, downgraded, or converted into misleading
success.

## Core move

Audit error paths for honesty. A failure should be observable by the role that
can act on it; fallback behavior is acceptable only when it is explicit,
traceable, and safe.

## Procedure

1. **Search changed code first.** Inspect `except`, `return None`, empty lists,
   default config fallbacks, subprocess handling, JSON/YAML parsing, network
   calls, and background process startup.
2. **Classify each fallback.** Decide whether it is safe recovery, deferred
   work, optional capability loss, or a hidden failure.
3. **Check observability.** Real failures should include logging, EACN status, a
   raised exception, or a persisted diagnostic artifact depending on context.
4. **Preserve useful tolerance.** Do not remove graceful degradation when the
   caller can still make a correct decision.
5. **Patch high-confidence issues.** Convert silent failures to explicit errors,
   warnings, or structured status values in the local style.
6. **Verify a negative path.** Add or run a focused test when the bug is in a
   shared helper, lifecycle path, or user-facing command.

## When to invoke

- Code introduces or changes exception handling, subprocess calls, network
  requests, config loading, project state persistence, or background services.
- A smoke test passes while logs show hidden errors.
- Reviewer, Ethics, or Gru asks whether a failure was surfaced honestly.

## Pitfalls

- Turning optional best-effort behavior into hard failure.
- Logging secrets or tokens while improving diagnostics.
- Raising inside cleanup paths where a clearer status return is safer.
- Auditing only Python exceptions and missing shell return codes.

## Output habit

Report each silent-failure risk as `verified`, `patched`, or `accepted fallback`,
with the evidence path and the reason the caller can or cannot act on it.
