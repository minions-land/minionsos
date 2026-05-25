---
id: mos_issue_report
kind: tool
domain: debug
auth: [gru, coder, ethics, writer, expert, noter]
source: minions/tools/mcp/runtime_tools.py:113
since: stable
keywords: [issue, report, bug, p0, p1, p2, escalate, drift]
related: [pitfall-tool-denied, pitfall-empty-authz, pitfall-deferred-schema]
status: stable
---

# mos_issue_report

**One line:** Universal — every role can call this, even with empty authz. File P0/P1/P2/P3 issues.

## Signature
```py
mos_issue_report(
  title: str,
  severity: "P0" | "P1" | "P2" | "P3",
  component: str,                # boundary|queue|scheduler|memory|eacn|lifecycle|viz|...
  summary: str,                  # cite paths + line numbers
  steps_to_reproduce: list[str] | None,
  evidence_refs: list[str] | None,
  suggested_fix: str | None,
) -> { issue_id, file_path }
```

## Severity guide
- **P0** — role unrunnable, project unrecoverable, data loss imminent.
- **P1** — major capability blocked, workaround exists.
- **P2** — annoyance, lossy, but not blocking.
- **P3** — nit.

## Universal escape hatch
This tool is in `_KEEPALIVE_TOOLS + _ISSUE_REPORT_TOOLS` spread into every
authz list. **If your role has empty authz** (the slug-suffix bug —
`pitfall-empty-authz`), even this tool is denied. Fall back to writing
directly to `project_<port>/issues/issues.jsonl` from a `Bash` tool —
project_37596 ISS-37596-1 was filed this way.

## Discipline
- Cite paths + line numbers + commit shas.
- For component=boundary / authz issues, name the exact `_normalise_role_name`
  branch that's wrong.
- Suggested fix: name the file:line you'd patch.
