# PITFALLS — patterns that burned real projects

Every entry here is grounded in `project_37596` (Grokking, May 2026) log evidence.
Read this BEFORE you do something risky. Each entry follows: **symptom → cause → recipe**.

## P-1. ToolSearch can't find an EACN tool, and the call fails

**Symptom (project_37596 / role-coder + role-ethics + role-noter logs):**
```
●The eacn3 tools are not in the deferred-tools index of THIS session — likely
  they're already loaded in my live tool inventory ...
●Error: ... eacn3_send_message — No such tool available
4 MCP servers failed · /mcp
```
Coder spent ~15 minutes thrashing on this; ethics filed an issue; noter looped on `mos_book_hot_update`.

**Cause:** the tool IS in the role's whitelist, but its **schema is deferred**. Calling it without first loading the schema fails. Or the role really IS denied (see P-2).

**Recipe:**
1. `ToolSearch(query="select:eacn3_send_message")` to load schema. **The exact tool name** must be in the `select:` list — the keyword search has missed `eacn3_*` for some users.
2. After ToolSearch, the call works.
3. If ToolSearch returns nothing for that name, you really are not whitelisted → file `mos_issue_report`.

---

## P-2. "tool not allowed for role 'X'" — the slug-suffix authz bug

**Symptom (project_37596 / `issues/issues.jsonl` ISS-37596-1, P0):**
```
Role 'theory-normalization-expert' has empty server_authz —
every MCP tool denied, event loop unrunnable
```
The role was spawned as `theory-normalization-expert` (slug-SUFFIX form) but `_normalise_role_name` only recognises `expert-<slug>` (slug-PREFIX). All MCP tools denied.

**Cause:** Always spawn experts as `mos_spawn_expert(name="<slug>")` — the launcher wraps it as `expert-<slug>` for you. Don't pass `<slug>-expert`.

**Recipe (Gru):**
- Use `mos_spawn_expert(name="theory-normalization")`, not `name="theory-normalization-expert"`.
- If you find an existing expert with the wrong shape: `mos_dismiss_role` + respawn with the correct slug.
- All roles (even broken ones) can call `mos_issue_report` because it's in the universal `_KEEPALIVE_TOOLS` / `_ISSUE_REPORT_TOOLS` set spread into every authz list — UNLESS the role has empty authz, in which case the issue must be written directly to `issues/issues.jsonl` from a Bash tool.

---

## P-3. Queue dead-launch FALSE positives — `{project_workspace}` not expanded

**Symptom (project_37596 / role-coder log, ISS-37596-10 / ISS-37596-14):**
```
status=oom exit_code=-9
bash: ... /MinionsOS/{project_workspace}/experiments/logs/exp-...: No such file or directory
```
But `metrics.csv` shows the run **completed all 30 000 steps and reached val_acc=1.0**.

**Cause:** `{project_workspace}` placeholder did not get substituted in `log_path`. The training command runs fine, but the post-run `.exit` marker write fails, and the supervisor's reaper marks the run as `oom`/`-9` / `dead-launch`. Retry budget then burns until exhaustion. **8 of 8 retries on b10p9_b20p9 cells were settled at `failed` despite each producing valid metrics.**

**Recipe (Coder):**
- Before submitting a sweep with `mos_exp_queue_submit`, **spot-check that `log_path` in the rendered cell contains an absolute project path, not the literal string `{project_workspace}`**.
- If you're already mid-sweep and seeing `oom exit_code=-9` on cells whose `metrics.csv` is intact, do not blindly retry: the queue will eat the retry budget. Pause via `mos_exp_queue_reconcile` after stopping the dispatcher, file `mos_issue_report`, and bulk-publish the actually-completed runs via `mos_publish_to_shared` from the on-disk `metrics.csv`.
- Do not call `mos_exp_queue_reconcile` defensively — only when there's something to reap. Repeated bare reconciles cost real time.

---

## P-4. `mos_adjudicate` is for project-final answers, not per-task closure

**Symptom (project_37596 / role-ethics log):**
```
mos_adjudicate ...
"submissions/answer.json doesn't exist"
```
Ethics tried to use it as a per-task closer because Gru asked to "adjudicate" pending events.

**Cause:** `mos_adjudicate` only fires on a final submission (`branches/shared/submissions/answer.json`), and only on profiles where `evaluation.adjudication.depth ∈ {single, panel}`. The default `scientific-paper` profile has `depth: none` and never adjudicates anything during the run.

**Recipe:**
- Mid-project verdicts → use `mos_book_resolve_contradiction` (Ethics) or `mos_signboard_evaluate` (consensus on phase transitions).
- End-of-project answer audit → only after `mos_submit` + only when the profile asks for it.

---

## P-5. Bash heredoc with CJK / LaTeX = empty `tool_use.input`

**Symptom (`Paper Crash` 2026-05-24 referenced from CLAUDE.md):**
```
InputValidationError: required parameter 'command' is missing
output_tokens: 47, 74, 25
```
Three consecutive `Bash` calls with `cat <<'EOF' ... EOF` for a long Chinese LaTeX comparison report. The model emitted `input: {}`.

**Cause:** Opus 4.7 has an observed empty-input failure mode on long structured-content tool inputs. Hard cap **~50 lines / ~3 KB per `tool_use.input`**.

**Recipe (every role):**
1. Seed file with one short `Write` (≤50 lines: preamble + closing token).
2. Append rest with successive `Edit` calls, each ≤50 lines.
3. **Never** stuff a long doc into a Bash heredoc.
4. The `reliable-file-io` skill at `minions/roles/common/skills/reliable-file-io.md` has the exact recipe.

---

## P-6. Subagent's "needs-experiment" verdicts are usually lazy boilerplate

**Symptom (project_37596 / role-ethics log):**
```
The subagent did boilerplate work — every "needs-experiment" verdict has a
one-line generic rationale "Substantive disagreement requires further
investigation" with a contradictory action ("Close as resolved.")
```

**Cause:** Spawning a subagent (`Agent` / `mcp__codex-subagent__codex`) and accepting its verdict without inspecting its trace.

**Recipe:**
- **Always grep the subagent's reel** before accepting a verdict involving > 3 items. Use `mos_reel_get(ref="<role>/<session_id>/<task_id>")` then `mos_reel_window(ref, span=10)` to see what it actually read.
- Don't ask one subagent to verdict 18 contradictions in one shot. Either chunk to 5-at-a-time or do the long-tail inline.

---

## P-7. `mos_query_gpus` rejected as "auto"

**Symptom (project_37596 / role-coder log):**
```
mos_query_gpus rejected auto — needs local.
```

**Cause:** `mos_query_gpus(execution="auto")` is rejected because the GPU listing must come from the project host, not auto-routed. Pass `execution="local"`.

---

## P-8. `mcp_minionsos` is not a Python module

**Symptom (project_37596 / role-noter log):**
```
ModuleNotFoundError: No module named 'mcp_minionsos'
```

**Cause:** The MCP server is `minions/tools/mcp/`, importable as `from minions.tools.mcp import mcp`. There is no top-level `mcp_minionsos`.

**Recipe:** If you really need to call a tool function from Python, import `from minions.tools.mcp.<file> import ...`. But you almost never need this — call the tool through the MCP surface.

---

## P-9. `pandas` / `torch` not in MinionsOS .venv

**Symptom (project_37596 / role-coder + role-expert-mathematician):**
```
ModuleNotFoundError: No module named 'pandas'
ModuleNotFoundError: No module named 'torch'
... no PROJECT venv
```

**Cause:** Roles run inside the MinionsOS uv env, which intentionally does NOT carry the project's data-science deps. The project has its own venv (or conda env) inside `branches/<role>/...` or under `parent_repo`.

**Recipe:**
- For ad-hoc analysis, use `mos_exp_run(execution="local", ...)` with the project's venv path baked into the command.
- For interactive scripts, `cd` into the project directory and `source .venv/bin/activate` first.
- Never `uv sync` from inside `branches/<role>/...` — that creates a nested `.venv` and breaks the role's MCP servers (project_37596 expert-mathematician hit `os error 17 File exists`).

---

## P-10. `cp` / `mv` into another role's branch

**Symptom:** No artifact appears in the destination role's worktree at next pull, or appears but commits get rejected.

**Cause:** Role branches are per-role git worktrees. Direct cross-branch writes bypass the shared lock and the publish whitelist.

**Recipe:** Always use `mos_publish_to_shared(role=<self>, src_path=..., dst_subpath=..., commit_message=...)`. The destination role reads from `branches/shared/<dst_subpath>`, not `branches/<other-role>/`. See `07-publish-handoffs.md`.

---

## P-11. "4 MCP servers failed · /mcp" appearing constantly

**Symptom (every role-*.log in project_37596):** the harness footer flashes `4 MCP servers failed · /mcp` for minutes at a time.

**Cause:** Cosmetic — usually one of `codex-subagent`, `keepalive`, `graphify`, or `playwright` is briefly unreachable while the project boots. The role's own `minionsos` and `eacn3` are still up. Don't react.

**Recipe:** Ignore unless YOUR specific tool fails. If it does, re-check ToolSearch and then `mos_issue_report`.

---

## P-12. Long bg task + no keepalive = stale prompt cache

**Symptom:** Subagent runs > 5 min, the model wakes up to a cold cache, costs jump.

**Recipe:** When dispatching `Agent(... run_in_background=true)` or `mcp__codex-subagent__codex(... run_in_background=true)`, immediately enter `mcp__keepalive__wait_bg(deadline_seconds=180, bg_ids=[...])`. The PostToolUse `bg_keepalive_nudge` hook reminds you of this.

---

## P-13. Don't use `eacn3_await_events` directly

**Cause:** Bypasses the project-aware wrapper, which delivers `suggested_tool` annotations and idle-checks. Use `mos_await_events` instead. Noter alone uses `mos_noter_wait` because it's not on EACN.

---

## P-14. `mos_book_query` returns the same orphan repeatedly

**Symptom (project_37596 / role-noter, role-ethics, multiple times):**
```
info ORPHAN_PAGE: `coder-p3-width-falsifier-cgrok-h-fails` —
No inbound wikilink from another book page.
```

**Cause:** Page was ingested but no other Book page links to it. `mos_book_lint` keeps surfacing it.

**Recipe:** Either (a) add a `[[wikilink]]` from a related page through `mos_book_save_synthesis`, or (b) accept it's a leaf and move on; the lint is a hint, not a blocker.
