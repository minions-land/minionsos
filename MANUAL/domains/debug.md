---
id: domain-debug
kind: domain
domain: debug
auth: ['*']
source: minions/tools/mcp/runtime_tools.py:1
since: stable
keywords: [issue, debug, error, denied, drift, triage, log]
related: [mos_issue_report, pitfall-tool-denied, pitfall-deferred-schema, pitfall-empty-authz]
status: stable
---

# Domain: Issues + debug

When something is wrong, file `mos_issue_report` first. It's universal — every
role has it, even when other tools are denied (it's in `_KEEPALIVE_TOOLS` +
`_ISSUE_REPORT_TOOLS` spread).

## Top tools

```bash
lookup.py --id mos_issue_report
lookup.py --pitfalls "denied"      # tool-not-allowed errors
lookup.py --pitfalls "queue"       # dead-launch FP, retry storm
```

## Triage map (symptom → page)

| Symptom | Reach for |
|---|---|
| "tool X — No such tool available" | `pitfall-deferred-schema` |
| "is not allowed for role 'Y'" | `pitfall-empty-authz`, `pitfall-tool-denied` |
| `InputValidationError: required parameter ... is missing` (tiny output_tokens) | `pitfall-opus-empty-input` |
| `ModuleNotFoundError: No module named 'pandas' / 'torch'` | `pitfall-project-venv` |
| `4 MCP servers failed · /mcp` | `pitfall-mcp-cosmetic` |
| Queue cells `failed` despite valid `metrics.csv` | `pitfall-queue-deadlaunch-fp` |
| Subagent boilerplate verdicts | `pitfall-subagent-boilerplate` |

## Log locations (when SSH-ing in)

| What | Where |
|---|---|
| Gru loop | `minions/state/logs/gru.log` |
| Project backend | `project_<port>/logs/backend.log` |
| Role runtime | `project_<port>/logs/role-<name>.log` |
| Issues | `project_<port>/issues/issues.jsonl` |
| Project metadata | `project_<port>/meta.json` |
| EACN3 SQLite | `project_<port>/eacn3_data/eacn3.db` |
| Experiment results | `project_<port>/branches/main/exp/exp-<id>/` |

## Strip ANSI before grep

Role logs contain ANSI escape sequences that break grep:
```bash
perl -pe "s/\x1b\[[0-9;]*[a-zA-Z]//g; s/\x1b\][^\x07]*\x07//g" role-expert.log | grep -iE "error|fail|denied"
```
