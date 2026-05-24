# 12 — Issues + debug triage

> **L2 card.** When something is wrong, file `mos_issue_report` first. It's a universal tool — every role has it, even when other tools are denied.
> Top tool: `mos_issue_report`. Plus a triage playbook for the common log patterns.

---

## mos_issue_report

```python
args:
  title: str
  severity: "P0" | "P1" | "P2" | "P3"
  component: str               # "boundary" | "queue" | "scheduler" | "memory" | "eacn" | "lifecycle" | "viz" | ...
  summary: str                 # what went wrong; cite paths + line numbers
  steps_to_reproduce: list[str] | None
  evidence_refs: list[str] | None
  suggested_fix: str | None
returns: { issue_id, file_path }
```

**Always universal.** Even when your role has empty server_authz (PITFALLS § P-2), the writer is `_KEEPALIVE_TOOLS + _ISSUE_REPORT_TOOLS` spread, so `mos_issue_report` works. If that ALSO fails, write directly to `issues/issues.jsonl` from a `Bash` tool — that's the documented fallback (project_37596 ISS-37596-1 used this path).

**Severities:**
- **P0** — role unrunnable, project unrecoverable, data loss imminent.
- **P1** — major capability blocked, workaround exists.
- **P2** — annoyance, lossy, but not blocking.
- **P3** — nit.

**Pattern: well-formed issue (project_37596 ISS-37596-1):**
```python
mos_issue_report(
  title="Role 'theory-normalization-expert' has empty server_authz — every MCP tool denied",
  severity="P0",
  component="boundary",
  summary=(
    "The expert role spawned for project 37596 is registered as "
    "`theory-normalization-expert` (slug-SUFFIX form). `_normalise_role_name()` "
    "in minions/config/__init__.py:791 only collapses the PREFIX form ..."
  ),
  steps_to_reproduce=[
    "Spawn an expert with a role name in slug-SUFFIX form, e.g. mos_spawn_expert(name='theory-normalization-expert').",
    "Observe gru.log: 'No server_authz entry for role=theory-normalization-expert'.",
    "Try any mos_* call from the role; all return 'not allowed'.",
  ],
  suggested_fix="Extend _normalise_role_name to recognise '<slug>-expert' suffix as well.",
)
```

---

## Triage playbook — what to do when a tool fails

### "tool X — No such tool available" / "is not allowed for role 'Y'"

| Step | Why |
|---|---|
| 1. `ToolSearch(query="select:<full_tool_name>")` | Loads deferred schema; many "no such tool" failures are just unloaded schemas. |
| 2. If still failing, check authz | grep `_SERVER_AUTHZ` in `minions/config/__init__.py` for your role's allowlist. |
| 3. If you're not in the list | `mos_issue_report` and route around: ask another role via `eacn3_send_message`. |

### "InputValidationError: required parameter X is missing" with tiny `output_tokens`

PITFALLS § P-5. The Opus 4.7 empty-input bug. **Don't retry the same big payload.** Switch to `reliable-file-io` Tier-0 seed-and-Edit. Cap `tool_use.input` at ~50 lines / ~3 KB.

### "ModuleNotFoundError: No module named 'pandas' / 'torch' / 'mcp_minionsos'"

PITFALLS § P-8 + P-9. Roles run in MinionsOS uv env, not the project's venv. For data-science work use `mos_exp_run(execution="local", ...)` with the project venv path. Don't `uv sync` from inside `branches/<role>/...`.

### "4 MCP servers failed · /mcp"

PITFALLS § P-11. Cosmetic. Ignore unless YOUR specific tool actually fails.

### Queue cells stuck in `failed` despite valid `metrics.csv`

PITFALLS § P-3. The dead-launch FP from unexpanded `{project_workspace}`. **Stop reconciling.** File `mos_issue_report`. Then bulk-publish the actually-completed runs by reading `metrics.csv` directly via `mos_publish_to_shared`.

### Subagent / Codex returned suspicious boilerplate verdicts

PITFALLS § P-6. Always `mos_reel_get` the subagent's transcript before accepting anything ≥ 3 items. Generic rationales like "Substantive disagreement requires further investigation" are red flags.

---

## Log locations (when SSH-ing in for triage)

| What | Where |
|---|---|
| Gru loop | `minions/state/logs/gru.log` |
| Project backend | `project_<port>/logs/backend.log` |
| Role runtime | `project_<port>/logs/role-<name>.log` |
| Issues | `project_<port>/issues/issues.jsonl` |
| Project metadata | `project_<port>/meta.json` |
| EACN3 SQLite | `project_<port>/eacn3_data/eacn3.db` |
| Experiment results | `project_<port>/branches/shared/exp/exp-<id>/` |
| Signboard | `project_<port>/branches/shared/governance/signboard.json` |

ANSI sequences in role logs make `grep` noisy — strip them first:
```bash
perl -pe "s/\x1b\[[0-9;]*[a-zA-Z]//g; s/\x1b\][^\x07]*\x07//g" role-coder.log | grep -iE "error|fail|denied"
```
