---
slug: silent-failure-audit
summary: Audit error paths for honesty — find places where errors are swallowed, downgraded, or converted into misleading success.
layer: logical
tools:
version: 2
status: active
supersedes:
references: test-coverage-review
provenance: human
---

# Skill — Silent Failure Audit

Honest error paths: a failure must be observable by the role that can act on it. Fallback behavior is acceptable only when it is explicit, traceable, and safe.

## When to invoke

- Code introduces or changes exception handling, subprocess calls, network requests, config loading, project state persistence, or background services.
- A smoke test passes while logs show hidden errors.
- Reviewer, Ethics, or Gru asks whether a failure was surfaced honestly.

## Structure

Each fallback gets one of three classifications: **verified** (safe recovery, observable), **patched** (silent failure converted to explicit error / warning / structured status), or **accepted fallback** (graceful degradation with a clear reason the caller can still decide). Observability is via logging, EACN status, raised exception, or persisted diagnostic artifact — pick the form that matches the call site.

## Procedure

1. **Search changed code first.** Inspect `except`, `return None`, empty lists, default config fallbacks, subprocess handling, JSON/YAML parsing, network calls, and background process startup.
2. **Classify each fallback.** Safe recovery, deferred work, optional capability loss, or hidden failure.
3. **Check observability.** Real failures need logging, EACN status, a raised exception, or a persisted diagnostic artifact depending on context.
4. **Preserve useful tolerance.** Do not remove graceful degradation when the caller can still make a correct decision.
5. **Patch high-confidence issues.** Convert silent failures to explicit errors, warnings, or structured status values in the local style.
6. **Verify a negative path.** Add or run a focused test when the bug is in a shared helper, lifecycle path, or user-facing command.
7. **Report** each silent-failure risk as `verified`, `patched`, or `accepted fallback`, with the evidence path and the reason the caller can or cannot act on it.

## Pitfalls

- Turning optional best-effort behavior into hard failure.
- Logging secrets or tokens while improving diagnostics.
- Raising inside cleanup paths where a clearer status return is safer.
- Auditing only Python exceptions and missing shell return codes.
