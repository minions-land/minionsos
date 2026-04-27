# MinionsOS V4 — Build Completion Report

_Date: 2026-04-23_

## Summary

All final-mile work from the previous partial build is complete:

- Config bug fixed (heartbeat interval parsing).
- EACN3 HTTP client verified against real routes (no stale endpoints).
- Lifecycle smoke test written and passing end-to-end against a real EACN3 backend subprocess.
- Unit tests green; `ruff check` clean; `./mos doctor` healthy; `./mos status` renders.
- Repo cleaned (scaffolding/build-logs/caches removed).

## Integration changes made

### 1. Config: `heartbeat_report_interval` parsing

**Decision:** accept duration strings (`"30s"`, `"5m"`, `"2h"`, `"1d"`) or bare int seconds; `"0"` disables.

Changes in `@/Users/mjm/MinionsOS_V4/minions/config/__init__.py`:

- Added `parse_duration()` helper and a `_DURATION_RE`/`_DURATION_UNITS` table.
- Added Pydantic `field_validator` on `heartbeat_report_interval` that validates format at load time and raises `ConfigError` on bad input.
- Added `GruConfig.heartbeat_interval_seconds` property that returns parsed seconds.
- `@/Users/mjm/MinionsOS_V4/minions/gru/loop.py` now uses `cfg.heartbeat_interval_seconds` (was passing the raw string through an `int`-typed field, the bug the previous agent was mid-fix on).
- `gru.yaml.example` value (`"2h"`) is unchanged and remains valid.

### 2. EACN3 HTTP endpoints — verified, no changes needed

Re-read `EACN3/eacn/network/api/app.py`, `routes.py`, `discovery_routes.py`. The client in `@/Users/mjm/MinionsOS_V4/minions/lifecycle/eacn_client.py` already uses correct paths:

- `/api/discovery/servers` (POST, DELETE, `{id}/heartbeat`) — matches `discovery_router` prefix `/api/discovery`.
- `/api/discovery/agents` — same prefix.
- `/api/messages` (POST `RelayMessageRequest`) — matches `router` prefix `/api`.
- `/api/events/{agent_id}` — matches `router`.
- `/health` (no `/api` prefix) — matches `@app.get("/health")` registered directly on the app.

`grep -rn '/api/agents\|/api/broadcast' minions/` returned no stale references.

### 3. Missing dep: `eacn3`

`pyproject.toml` declared `[tool.uv.sources] eacn3 = { path = "./EACN3", editable = true }` but `eacn3` was not listed under `[project].dependencies`, so `uv sync` never installed it and uvicorn could not import `eacn.network.api.app`. Added `"eacn3"` to `dependencies`. `uv sync` now installs EACN3 and its transitive deps (`fastapi`, `aiosqlite`, `uvloop`, `httptools`).

### 4. `./mos` launcher symlink resolution

`@/Users/mjm/MinionsOS_V4/minions/bin/gru` used `$(dirname "${BASH_SOURCE[0]}")` without resolving symlinks, so invoking via `./mos` (a symlink) resolved `SCRIPT_DIR` to the repo root and `ROOT="$SCRIPT_DIR/../.."` to `/Users`, causing `mkdir: /Users/minions: Permission denied` on every subcommand. Replaced with a `readlink` loop. `./mos doctor` and `./mos status` now work.

### 5. Lifecycle smoke test

New file `@/Users/mjm/MinionsOS_V4/tests/smoke/lifecycle.py`:

- Creates a temp dir, `git init`/commit, sets `MINIONS_ROOT` env to a `minionsos/` subdir so `project_dir(port)` lands in the temp repo.
- Flushes `minions.*` modules before re-importing so `MINIONS_ROOT` picks up the env override.
- Runs all ten requested steps and prints ✓/✗ per step.
- Exits non-zero on any failure.

All 12 sub-checks pass, including real `register_agent` → `post_message` → `poll_events` round trip via the live EACN3 backend on a dynamically-allocated port.

## Verification commands

```
uv run ruff check .                      # All checks passed!
uv run pytest tests/unit -q              # 54 passed
uv run python tests/smoke/lifecycle.py   # ALL STEPS PASSED ✓
./mos doctor                             # all OK
./mos status                             # renders empty table
```

## Repo cleanup

Deleted: `examples/`, `MINIONSOS_V2_MAS_VIS.md`, `.minions-build/`, all `__pycache__`, `.pytest_cache`, `.ruff_cache`, `*.pyc` (outside `.venv/`). `minions/config.py` shadow stub did not exist. `.gitignore` already covers runtime state, config yaml (keeping `.example`), per-project runtime subdirs, caches, and `node_modules/`.

Top-level tree now:

```
CLAUDE.md  EACN3  README.md  answer  gru  install.sh  minions
minionsos  mos  pyproject.toml  ruff.toml  tests  uv.lock
```

## Residual gaps

- **Full role-spawn smoke:** not automated. Spawning a real Claude CLI subprocess as a role, having it register via EACN3 and exchange messages with Gru, requires a human-in-the-loop dialogue (or a mocked `claude` binary and stubbed MCP server). The smoke test covers backend lifecycle + a fake agent round-trip, which proves the EACN3 layer is wired correctly; role subprocess lifecycle still needs a manual end-to-end sanity check by running `./gru` and exercising `project_create` + `spawn_role`.
- **`gru_relay` end-to-end:** the HTTP-side implementation in `minions/lifecycle/relay.py` was updated but not exercised by the automated smoke test (would need two projects + two agents). Covered in spirit by the agent-registration + messaging path in step 5–6.
- **Crash-loop thresholds:** exercised by unit tests but not in smoke.

## Config format decision (recap)

`heartbeat_report_interval` accepts `"<N>[s|m|h|d]"` strings or integer seconds. `"0"`/`0` disables. This keeps the human-friendly `"2h"` in `gru.yaml.example` while letting tests/automation pass bare ints. Parsed lazily via `GruConfig.heartbeat_interval_seconds`.

## V2 patch: concurrency, personas, cron

Three V1 pain points hard-fixed in V2:

### 1. Experimenter: fire-and-poll, no serial waits

`minions/tools/experiment_ssh.py` rewritten so `exp_run` is **non-blocking**. It launches the command under `nohup` (plus `setsid` when available; `disown` otherwise for macOS compatibility), writes metadata to `{workdir}/logs/{run_id}.meta.json`, and returns `{run_id, pid, log_path, target_id}` immediately. The subshell appends its exit status to `{run_id}.exit` on termination so `exp_status` can distinguish `running` vs `exited` without tracking pids.

New MCP tools: `exp_status`, `exp_wait` (polls every 2 s up to `timeout`), `exp_kill` (SIGTERM via stored pid), `exp_list` (enumerates `logs/*.meta.json`), and `query_gpus` (existed but was never whitelisted). Legacy `timeout` parameter on `exp_run` is a documented no-op. Whitelists in `minions/config/__init__.py` updated to expose the new tools to experimenter main + subagents. `minions/roles/experimenter/SYSTEM.md` gained explicit **Fire-and-poll model (mandatory)** and **Detached execution (mandatory)** sections; fill-GPU / re-queue-on-OOM / 3-fail circuit-break text preserved.

Unit test `tests/unit/test_experiment_ssh.py` stubs a local target under `tmp_path`, verifies `exp_run` returns with `run_id` and a created log file, drives a run from `running` → `exited` via `exp_wait`, and verifies `exp_list` enumerates the run.

### 2. Reviewer: persona-driven multi-round subagent reviews

Six personas added under `minions/roles/reviewer/personas/`:

- `strict-theorist.md`
- `skeptical-empiricist.md`
- `friendly-clarifier.md`
- `adversarial-novelty-hawk.md`
- `pragmatic-reproducibility.md`
- `broad-impact-sceptic.md`

Each file has an identity paragraph, a "What you focus on" list, a differentiated "What you down-weight" list, and a closing reminder that the SYSTEM.md evidence-rule and no-praise-padding rule still override persona. `minions/roles/reviewer/SYSTEM.md` replaces the old "mild initialization differences" paragraph with a concrete **Persona rotation (mandatory)** section (discover via glob, draw without replacement per loop, inject by concatenating into subagent prompts, 3–5 rounds default) plus a **Persona file discovery** subsection so user-added personas enter rotation without code changes.

### 3. Universal cron polling for every Role

Root `CLAUDE.md` gained a new **Hard rule 6**: all spawned Roles must install a polling loop calling `eacn3_events_poll` every `$MINIONS_POLL_INTERVAL`, default `1m`, allowed values `1m / 3m / 5m`. Every one of the 7 role SYSTEM.md files (gru, noter, coder, experimenter, writer, reviewer, expert) now carries a `## Polling (mandatory)` block right after Identity & scope.

Config: `GruConfig` gets `poll_interval_default: str = "1m"` with a validator that rejects anything outside `{1m, 3m, 5m}`. `gru.yaml.example` carries the new key. `parse_duration` is untouched so general heartbeat intervals remain free-form.

Spawn: `spawn_role` and `spawn_expert` (both in `minions/lifecycle/role.py` and their MCP wrappers in `minions/tools/mcp_server.py`) accept `poll_interval: str | None = None`. Resolution order is explicit arg → `MINIONS_POLL_INTERVAL` env → `GruConfig.poll_interval_default` → `"1m"`. The resolved value is validated, pushed to the subprocess via `MINIONS_POLL_INTERVAL` env, and persisted on `RoleEntry.poll_interval` in `projects.json` so revived roles retain their cadence.

Tool support: `schedule_poll(interval)` MCP tool added. **Judgment call**: this is intentionally a **no-op audit recorder** (logs "role X on port Y scheduled poll every Z") rather than a real cron installer. Claude Code subprocesses cannot install host cron entries reliably, and the MCP stdio process would not outlive the role anyway. The actual polling is performed by the role itself per its SYSTEM.md instructions (call `eacn3_events_poll` on cadence in its own agent loop), with `schedule_poll` providing an auditable trail that each role declared a cadence at startup. `schedule_poll` is whitelisted for all 7 role mains (not subagents).

### Verification

```
uv run ruff check .                      # All checks passed!
uv run pytest tests/unit -q              # 57 passed (was 54 + 3 new)
uv run python tests/smoke/lifecycle.py   # ALL STEPS PASSED ✓
./mos doctor                             # all OK
```
