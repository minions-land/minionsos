"""Experiment execution MCP tools for the Coder role.

These tools are loaded for the ``coder`` role.
Runtime whitelisting is enforced by MinionsOS; Claude also receives the
allowlist at spawn time via ``--allowed-tools``, while Codex is constrained
by MCP server-side authorization.

All execution is **fire-and-poll**: ``exp_run`` launches the command fully
detached via ``nohup``/``setsid`` and returns immediately with a ``run_id``.
Use ``exp_status``/``exp_wait``/``exp_list`` to observe progress and
``exp_kill`` to terminate. Batch queue tools maintain a project-level
SQLite-backed pending pool so Coder can submit work and let Python keep
GPUs filled without spending agent tokens on scheduling loops.

Tools:
- exp_run      — detached launch, returns immediately with run_id + pid + log_path
- exp_status   — check a run (running | exited, exit_code, log_tail)
- exp_wait     — poll up to timeout for a run to exit
- exp_kill     — SIGTERM a run
- exp_list     — list all runs on a target (from meta files)
- exp_put      — upload a file to a target
- exp_get      — download a file from a target (refuses if > 500 MB)
- exp_tail     — tail a log file on a target
- query_gpus   — list free GPU memory on a target
- exp_queue_*  — project-level fluid GPU scheduler and dynamic GPU pool
"""

from __future__ import annotations

import json
import logging
import shlex
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

from minions.config import LocalTarget, SSHTarget, load_experiment_targets
from minions.errors import ConfigError, ExperimentError
from minions.tools.experiment_scheduler import ExperimentScheduler, QueueUnit

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Size limit
# ---------------------------------------------------------------------------

MAX_DOWNLOAD_BYTES = 500 * 1024 * 1024  # 500 MB

# ---------------------------------------------------------------------------
# Run-state types
# ---------------------------------------------------------------------------

ExperimentRunState = Literal["running", "exited"]


class ExperimentRunStatus(TypedDict, total=False):
    """Shape returned by ``_local_status`` / ``_ssh_status`` / ``exp_status``."""

    state: ExperimentRunState
    exit_code: int
    log_tail: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _expand_workdir(workdir: str) -> str:
    """Expand template tokens in a target's ``workdir`` string.

    Supported tokens:
    - ``{project_workspace}`` → absolute path of the current project's main
      branch worktree (``project_{port}/branches/main``), resolved from the
      ``MINIONS_PROJECT_PORT`` env var. Raises ``ConfigError`` if the token
      is present but the env var is absent (GitHub Issue #20: unresolved
      templates in log_path cause silent launch failures).
    """
    import os

    if "{project_workspace}" in workdir:
        port_s = os.environ.get("MINIONS_PROJECT_PORT")
        if port_s and port_s.isdigit():
            from minions.paths import project_workspace as _pws

            workdir = workdir.replace("{project_workspace}", str(_pws(int(port_s)).resolve()))
        else:
            raise ConfigError(
                f"workdir contains {{project_workspace}} but MINIONS_PROJECT_PORT is not set. "
                f"Cannot resolve template. workdir={workdir!r}"
            )
    return workdir


def _resolve_workdir(
    target_id: str,
) -> tuple[Literal["local", "ssh"], str, str | None, str | None]:
    """Return (type, workdir, host, key) for *target_id*."""
    cfg = load_experiment_targets()
    target = cfg.get_target(target_id)
    workdir = _expand_workdir(target.workdir)
    if isinstance(target, LocalTarget):
        return "local", workdir, None, None
    if isinstance(target, SSHTarget):
        return "ssh", workdir, target.host, target.key
    raise ConfigError(f"Unsupported target type: {target.type!r}")


def _ssh_cmd(host: str, key: str, remote_cmd: str) -> list[str]:
    return [
        "ssh",
        "-i",
        key,
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "BatchMode=yes",
        host,
        remote_cmd,
    ]


def _new_run_id() -> str:
    return "exp-" + uuid.uuid4().hex[:8]


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(tz=UTC).isoformat()


def _resolve_target_id(target_id: str) -> str:
    if target_id != "auto":
        return target_id
    cfg = load_experiment_targets()
    active = cfg.active_targets()
    if not active:
        raise ConfigError("No experiment targets configured.")
    return active[0].id


def _local_paths(workdir: str, run_id: str) -> tuple[Path, Path, Path, Path]:
    logs_dir = Path(workdir) / "logs"
    log_path = logs_dir / f"{run_id}.log"
    meta_path = logs_dir / f"{run_id}.meta.json"
    exit_path = logs_dir / f"{run_id}.exit"
    return logs_dir, log_path, meta_path, exit_path


def _remote_paths(workdir: str, run_id: str) -> tuple[str, str, str, str]:
    logs_dir = f"{workdir}/logs"
    return (
        logs_dir,
        f"{logs_dir}/{run_id}.log",
        f"{logs_dir}/{run_id}.meta.json",
        f"{logs_dir}/{run_id}.exit",
    )


def _build_launch_script(
    cmd: str,
    workdir: str,
    log_path: str,
    exit_path: str,
    env: dict[str, str] | None = None,
) -> str:
    """Build the nohup/setsid detached launcher.

    Runs the user cmd in a subshell, captures its exit code into ``exit_path``
    after it terminates, and echoes the child PID on stdout. ``setsid`` is
    used when present to fully detach from the controlling terminal; when
    absent (e.g. macOS default install) ``nohup`` + ``disown`` is sufficient.

    *env*: optional mapping of variables to ``export`` inside the subshell
    before invoking *cmd*. We export (not inline ``VAR=value command``)
    because the inline form is fragile across the ``nohup setsid bash -c``
    chain — CUDA libraries read ``CUDA_VISIBLE_DEVICES`` at C-extension
    init time, and on some launcher paths the inline binding does not
    propagate by the time PyTorch loads. See GitHub Issue #19.
    """
    export_lines = ""
    if env:
        export_lines = "".join(f"export {k}={shlex.quote(v)}; " for k, v in env.items())
    inner = (
        f"cd {shlex.quote(workdir)} && ( {export_lines}{cmd} ); echo $? > {shlex.quote(exit_path)}"
    )
    # Prefer setsid for full session detachment, but fall back gracefully.
    detach = "if command -v setsid >/dev/null 2>&1; then DETACH=setsid; else DETACH=; fi; "
    return (
        f"mkdir -p {shlex.quote(str(Path(log_path).parent))} && "
        f"{detach}"
        f"nohup $DETACH bash -c {shlex.quote(inner)} "
        f"> {shlex.quote(log_path)} 2>&1 < /dev/null & "
        f"PID=$!; disown 2>/dev/null || true; echo $PID"
    )


def _read_tail(path: Path, lines: int = 50) -> str:
    if not path.exists():
        return ""
    try:
        result = subprocess.run(
            ["tail", "-n", str(lines), str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout
    except Exception:
        return ""


def _ssh_tail(host: str, key: str, remote_path: str, lines: int = 50) -> str:
    result = subprocess.run(
        _ssh_cmd(host, key, f"tail -n {lines} {shlex.quote(remote_path)} 2>/dev/null || true"),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout


# ---------------------------------------------------------------------------
# Argument models
# ---------------------------------------------------------------------------


class ExpRunArgs(BaseModel):
    target_id: str = Field(description="Target ID from experiment_targets.yaml, or 'auto'.")
    cmd: str = Field(description="Shell command to run on the target.")
    gpu_ids: list[int] | None = Field(
        default=None,
        description="GPU IDs to expose via CUDA_VISIBLE_DEVICES.",
    )


class ExpStatusArgs(BaseModel):
    target_id: str
    run_id: str


class ExpWaitArgs(BaseModel):
    target_id: str
    run_id: str
    timeout: int = Field(default=60, description="Max seconds to poll for exit.")


class ExpKillArgs(BaseModel):
    target_id: str
    run_id: str


class ExpListArgs(BaseModel):
    target_id: str


class ExpPutArgs(BaseModel):
    target_id: str
    local_path: str = Field(description="Absolute local path to upload.")
    remote_rel_path: str = Field(description="Relative path inside target workdir.")


class ExpGetArgs(BaseModel):
    target_id: str
    remote_rel_path: str = Field(description="Relative path inside target workdir.")
    local_path: str = Field(description="Absolute local destination path.")


class ExpTailArgs(BaseModel):
    target_id: str
    rel_log_path: str = Field(description="Relative log path inside target workdir.")
    lines: int = Field(default=100, description="Number of tail lines.")


class QueryGpusArgs(BaseModel):
    target_id: str = Field(description="Target ID to query GPUs on.")


class ExpQueueUnitArgs(BaseModel):
    cmd: str = Field(description="Shell command to run for this experiment unit.")
    target_id: str = Field(
        default="auto",
        description="Target constraint: 'auto' or a configured target id.",
    )
    gpu_ids: list[int] | None = Field(
        default=None,
        description="Optional explicit physical GPU ids. If set, the unit waits for these GPUs.",
    )
    gpus_needed: int = Field(default=1, ge=1, description="Number of GPUs required.")
    min_free_mb: int = Field(default=0, ge=0, description="Minimum free VRAM required.")
    reserve_mb: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Soft VRAM reservation used by the scheduler. Defaults to max(min_free_mb, 8192)."
        ),
    )
    priority: int = Field(default=0, description="Higher priority pending units run first.")
    max_retries: int = Field(
        default=3,
        ge=0,
        description=(
            "OOM retry budget. Each retry escalates reserve_mb by ~1.5x so the "
            "scheduler picks a roomier GPU on the next attempt."
        ),
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExpQueueSubmitArgs(BaseModel):
    units: list[ExpQueueUnitArgs] = Field(description="Experiment units to append.")
    requester: str | None = Field(default=None, description="Logical requester or EACN source.")
    batch_id: str | None = Field(default=None, description="Optional caller-provided batch id.")
    metadata: dict[str, Any] = Field(default_factory=dict)
    reconcile: bool = Field(default=True, description="Immediately run Python-side scheduling.")
    project_port: int | None = Field(
        default=None,
        description="Project port. Defaults to MINIONS_PROJECT_PORT.",
    )


class ExpQueueReconcileArgs(BaseModel):
    batch_id: str | None = Field(default=None, description="Optional batch id filter.")
    project_port: int | None = Field(default=None)


class ExpQueueStatusArgs(BaseModel):
    batch_id: str | None = Field(default=None, description="Optional batch id filter.")
    project_port: int | None = Field(default=None)


class ExpQueueGpuPoolSetArgs(BaseModel):
    target_id: str = Field(default="all", description="'all' or one configured target id.")
    allowed_gpu_ids: list[int] | str = Field(
        default="all",
        description="'all' or explicit physical GPU ids available for new runs.",
    )
    draining: bool = Field(
        default=True,
        description="When shrinking the pool, let already-running jobs finish by default.",
    )
    evict: bool = Field(
        default=False,
        description=(
            "If True, immediately SIGTERM runs on GPUs being removed from the "
            "allowlist and reset their units to pending so the next reconcile "
            "places them on remaining allowed GPUs. Use when the operator says "
            "'I need these cards back NOW'. Caller's command should trap "
            "SIGTERM to checkpoint weights."
        ),
    )
    reason: str | None = Field(default=None)
    reconcile: bool = Field(default=True)
    project_port: int | None = Field(default=None)


class ExpQueueGpuPoolGetArgs(BaseModel):
    project_port: int | None = Field(default=None)


class ExpQueuePlanArgs(BaseModel):
    units: list[ExpQueueUnitArgs] = Field(
        description="Experiment units to dry-run against the live GPU snapshot."
    )
    project_port: int | None = Field(
        default=None,
        description="Project port. Defaults to MINIONS_PROJECT_PORT.",
    )


# ---------------------------------------------------------------------------
# exp_run — fire-and-poll
# ---------------------------------------------------------------------------


def exp_run(args: ExpRunArgs) -> dict:
    """Launch a command **detached** on a local or SSH target, return immediately.

    Returns ``{run_id, pid, log_path, target_id}``. The command runs under
    ``nohup setsid`` so closing the SSH session or the calling agent does
    not kill it. Use ``exp_status`` / ``exp_wait`` to observe progress.
    """
    target_id = _resolve_target_id(args.target_id)
    kind, workdir, host, key = _resolve_workdir(target_id)

    run_id = _new_run_id()
    # Expand {project_workspace} in the cmd string so scheduler-driven
    # relaunches don't leak the literal token to bash. Without this,
    # bash silently creates a real directory named `{project_workspace}`
    # under cwd and the supervisor's exit-marker check (which uses the
    # expanded path) falsely reports dead-launch (GitHub Issue #24).
    # _expand_workdir raises ConfigError if the token is present but
    # MINIONS_PROJECT_PORT is missing, sibling to the #20 fix.
    cmd = _expand_workdir(args.cmd)
    # Set CUDA_VISIBLE_DEVICES via shell `export` injected into the launch
    # script rather than as an inline `VAR=value command` prefix on the
    # command string. The inline form was unreliable across the
    # nohup/setsid chain (GitHub Issue #19): the env var bound to the
    # outer bash but did not consistently propagate to the python process
    # in time for CUDA library init, so all runs clustered on GPU 0.
    launch_env: dict[str, str] = {}
    if args.gpu_ids is not None:
        launch_env["CUDA_VISIBLE_DEVICES"] = ",".join(str(g) for g in args.gpu_ids)

    logger.info("exp_run target=%s run_id=%s cmd=%r (detached)", target_id, run_id, cmd[:120])

    meta: dict[str, object] = {
        "run_id": run_id,
        "cmd": cmd,
        "started_at": _now_iso(),
        "gpu_ids": args.gpu_ids,
        "target_id": target_id,
    }

    if kind == "local":
        logs_dir, log_path, meta_path, exit_path = _local_paths(workdir, run_id)
        logs_dir.mkdir(parents=True, exist_ok=True)
        script = _build_launch_script(cmd, workdir, str(log_path), str(exit_path), env=launch_env)
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ExperimentError(f"Failed to launch local run {run_id}: {result.stderr}")
        try:
            pid = int(result.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError) as exc:
            raise ExperimentError(f"Could not parse launch pid: {result.stdout!r}") from exc
        meta["pid"] = pid
        meta_path.write_text(json.dumps(meta, indent=2))
        return {
            "run_id": run_id,
            "pid": pid,
            "log_path": str(log_path),
            "target_id": target_id,
        }

    # ssh branch
    assert host and key
    _logs_dir, log_path_s, meta_path_s, exit_path_s = _remote_paths(workdir, run_id)
    launch = _build_launch_script(cmd, workdir, log_path_s, exit_path_s, env=launch_env)
    result = subprocess.run(
        _ssh_cmd(host, key, f"bash -lc {shlex.quote(launch)}"),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ExperimentError(f"SSH launch failed for {run_id}: {result.stderr}")
    try:
        pid = int(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise ExperimentError(f"Could not parse launch pid: {result.stdout!r}") from exc
    meta["pid"] = pid
    meta_blob = json.dumps(meta, indent=2)
    # Write meta on the remote side.
    write_meta = (
        f"cat > {shlex.quote(meta_path_s)} <<'__MINIONS_META__'\n{meta_blob}\n__MINIONS_META__"
    )
    subprocess.run(
        _ssh_cmd(host, key, write_meta),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "run_id": run_id,
        "pid": pid,
        "log_path": log_path_s,
        "target_id": target_id,
    }


# ---------------------------------------------------------------------------
# exp_status / exp_wait / exp_kill / exp_list
# ---------------------------------------------------------------------------


def _read_meta_pid(meta_path: Path) -> int | None:
    try:
        meta = json.loads(meta_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    pid = meta.get("pid")
    return int(pid) if isinstance(pid, int) else None


def _local_status(workdir: str, run_id: str) -> ExperimentRunStatus:
    _logs_dir, log_path, meta_path, exit_path = _local_paths(workdir, run_id)
    if not meta_path.exists():
        raise ExperimentError(f"Unknown run_id: {run_id}")
    log_tail = _read_tail(log_path, lines=50)
    if exit_path.exists():
        try:
            exit_code = int(exit_path.read_text().strip() or "0")
        except ValueError:
            exit_code = -1
        return {"state": "exited", "exit_code": exit_code, "log_tail": log_tail}
    # No .exit file yet — but if the bash wrapper is dead (kill -9, OS reboot,
    # OOM killer, etc.) the .exit will never be written. Probe the PID so we
    # don't mark a corpse as 'running' forever.
    pid = _read_meta_pid(meta_path)
    if pid is not None:
        try:
            import os

            os.kill(pid, 0)  # signal 0 = existence check, doesn't actually signal
        except ProcessLookupError:
            return {
                "state": "exited",
                "exit_code": -9,  # sentinel: killed before .exit was written
                "log_tail": log_tail,
            }
        except PermissionError:
            # PID exists but owned by another user — still alive enough for us.
            pass
    return {"state": "running", "log_tail": log_tail}


def _ssh_status(host: str, key: str, workdir: str, run_id: str) -> ExperimentRunStatus:
    _logs_dir, log_path, meta_path, exit_path = _remote_paths(workdir, run_id)
    # Combined probe: read pid out of meta, check exit file, check pid alive.
    # Output is one of:
    #   MISSING                     — meta gone, run unknown
    #   EXITED <code>               — .exit file present
    #   DEAD                        — .exit absent and pid no longer in /proc
    #   RUNNING                     — .exit absent and pid alive (or unknown pid)
    check = (
        f"if [ ! -f {shlex.quote(meta_path)} ]; then echo MISSING; exit 0; fi; "
        f"if [ -f {shlex.quote(exit_path)} ]; then "
        f"  echo EXITED; cat {shlex.quote(exit_path)}; exit 0; "
        f"fi; "
        f"PID=$(python3 -c \"import json,sys; print(json.load(open('{meta_path}'))"
        f".get('pid',''))\" 2>/dev/null); "
        f'if [ -n "$PID" ] && [ ! -d "/proc/$PID" ]; then echo DEAD; '
        f"else echo RUNNING; fi"
    )
    result = subprocess.run(
        _ssh_cmd(host, key, check),
        capture_output=True,
        text=True,
        check=False,
    )
    lines = result.stdout.strip().splitlines()
    if not lines or lines[0] == "MISSING":
        raise ExperimentError(f"Unknown run_id: {run_id}")
    log_tail = _ssh_tail(host, key, log_path)
    if lines[0] == "EXITED":
        try:
            exit_code = int(lines[1].strip()) if len(lines) > 1 else -1
        except ValueError:
            exit_code = -1
        return {"state": "exited", "exit_code": exit_code, "log_tail": log_tail}
    if lines[0] == "DEAD":
        # Wrapper PID gone but no .exit file: process was killed (SIGKILL,
        # OS reboot, OOM-killer) before it could record an exit code. Treat
        # as exited with -9 sentinel so the scheduler can fail the run
        # instead of polling forever.
        return {"state": "exited", "exit_code": -9, "log_tail": log_tail}
    return {"state": "running", "log_tail": log_tail}


def exp_status(args: ExpStatusArgs) -> ExperimentRunStatus:
    """Check run state. Returns ``{state, exit_code?, log_tail}``."""
    target_id = _resolve_target_id(args.target_id)
    kind, workdir, host, key = _resolve_workdir(target_id)
    if kind == "local":
        return _local_status(workdir, args.run_id)
    assert host and key
    return _ssh_status(host, key, workdir, args.run_id)


def exp_wait(args: ExpWaitArgs) -> ExperimentRunStatus:
    """Poll every 2 s up to *timeout* seconds for the run to exit."""
    target_id = _resolve_target_id(args.target_id)
    kind, workdir, host, key = _resolve_workdir(target_id)
    deadline = time.monotonic() + max(0, args.timeout)
    while True:
        if kind == "local":
            status = _local_status(workdir, args.run_id)
        else:
            assert host and key
            status = _ssh_status(host, key, workdir, args.run_id)
        if status["state"] == "exited":
            return status
        if time.monotonic() >= deadline:
            return status
        time.sleep(2.0)


def exp_kill(args: ExpKillArgs) -> dict:
    """Send SIGTERM to a running exp_run process."""
    target_id = _resolve_target_id(args.target_id)
    kind, workdir, host, key = _resolve_workdir(target_id)
    _logs_dir, _log_path, meta_path, _exit_path = (
        _local_paths(workdir, args.run_id)
        if kind == "local"
        else _remote_paths(workdir, args.run_id)  # type: ignore[assignment]
    )
    if kind == "local":
        mp = Path(meta_path)  # type: ignore[arg-type]
        if not mp.exists():
            raise ExperimentError(f"Unknown run_id: {args.run_id}")
        meta = json.loads(mp.read_text())
        pid = int(meta["pid"])
        try:
            import os
            import signal

            # Prefer killing the whole process group so children (the actual
            # workload, traps, dataloaders) get the signal — not just the
            # outer bash wrapper. exp_run uses setsid which makes the launched
            # PID the group leader. Fall back to single-PID kill if killpg
            # is unavailable or the group doesn't exist (no-setsid fallback).
            try:
                os.killpg(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                os.kill(pid, signal.SIGTERM)
            return {"killed": True, "pid": pid}
        except ProcessLookupError:
            return {"killed": False, "pid": pid}
    assert host and key
    meta_path_str = str(meta_path)
    # Same logic remotely: try the process group first (kill -- -PID), fall
    # back to single PID if the kernel says ESRCH (typically because we ran
    # in fallback no-setsid mode). The 2 s grace lets the trap handler
    # write its checkpoint before SIGTERM is delivered to the child.
    cmd = (
        f"if [ -f {shlex.quote(meta_path_str)} ]; then "
        f"  PID=$(python3 -c \"import json;print(json.load(open('{meta_path_str}'))['pid'])\"); "
        f"  if kill -TERM -- -$PID 2>/dev/null; then echo OK; "
        f"  elif kill -TERM $PID 2>/dev/null; then echo OK; "
        f"  else echo GONE; fi; "
        f"else echo MISSING; fi"
    )
    result = subprocess.run(
        _ssh_cmd(host, key, cmd),
        capture_output=True,
        text=True,
        check=False,
    )
    out = result.stdout.strip()
    if "MISSING" in out:
        raise ExperimentError(f"Unknown run_id: {args.run_id}")
    return {"killed": "OK" in out}


def exp_list(args: ExpListArgs) -> list[dict]:
    """List all runs on *target_id* by scanning ``logs/*.meta.json``."""
    target_id = _resolve_target_id(args.target_id)
    kind, workdir, host, key = _resolve_workdir(target_id)
    runs: list[dict] = []
    if kind == "local":
        logs_dir = Path(workdir) / "logs"
        if not logs_dir.exists():
            return []
        for meta_file in sorted(logs_dir.glob("*.meta.json")):
            try:
                meta = json.loads(meta_file.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            run_id = meta.get("run_id")
            if not run_id:
                continue
            try:
                status = _local_status(workdir, run_id)
                state = status["state"]
            except ExperimentError:
                state = "unknown"
            runs.append(
                {
                    "run_id": run_id,
                    "state": state,
                    "started_at": meta.get("started_at"),
                    "cmd": meta.get("cmd"),
                    "target_id": meta.get("target_id"),
                    "gpu_ids": meta.get("gpu_ids"),
                    "pid": meta.get("pid"),
                    "log_path": str(_local_paths(workdir, run_id)[1]),
                }
            )
        return runs
    assert host and key
    listing = subprocess.run(
        _ssh_cmd(host, key, f"ls {shlex.quote(workdir + '/logs')}/*.meta.json 2>/dev/null || true"),
        capture_output=True,
        text=True,
        check=False,
    )
    for line in listing.stdout.strip().splitlines():
        meta_path = line.strip()
        if not meta_path:
            continue
        cat = subprocess.run(
            _ssh_cmd(host, key, f"cat {shlex.quote(meta_path)}"),
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            meta = json.loads(cat.stdout)
        except json.JSONDecodeError:
            continue
        run_id = meta.get("run_id")
        if not run_id:
            continue
        try:
            status = _ssh_status(host, key, workdir, run_id)
            state = status["state"]
        except ExperimentError:
            state = "unknown"
        runs.append(
            {
                "run_id": run_id,
                "state": state,
                "started_at": meta.get("started_at"),
                "cmd": meta.get("cmd"),
                "target_id": meta.get("target_id"),
                "gpu_ids": meta.get("gpu_ids"),
                "pid": meta.get("pid"),
                "log_path": _remote_paths(workdir, run_id)[1],
            }
        )
    return runs


# ---------------------------------------------------------------------------
# exp_put / exp_get / exp_tail / query_gpus (unchanged)
# ---------------------------------------------------------------------------


def exp_put(args: ExpPutArgs) -> dict:
    """Upload a local file to a target's workdir."""
    kind, workdir, host, key = _resolve_workdir(args.target_id)
    local = Path(args.local_path)
    if not local.exists():
        raise ExperimentError(f"Local file not found: {local}")

    if kind == "local":
        import shutil

        dest = Path(workdir) / args.remote_rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local, dest)
        logger.info("exp_put local: %s → %s", local, dest)
        return {"ok": True, "dest": str(dest)}
    assert host and key
    remote_dest = f"{workdir}/{args.remote_rel_path}"
    result = subprocess.run(
        [
            "scp",
            "-i",
            key,
            "-o",
            "StrictHostKeyChecking=no",
            str(local),
            f"{host}:{remote_dest}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ExperimentError(f"scp failed: {result.stderr}")
    logger.info("exp_put ssh: %s → %s:%s", local, host, remote_dest)
    return {"ok": True, "dest": remote_dest}


def exp_get(args: ExpGetArgs) -> dict:
    """Download a file from a target's workdir. Refuses if > 500 MB."""
    kind, workdir, host, key = _resolve_workdir(args.target_id)
    local_dest = Path(args.local_path)

    if kind == "local":
        src = Path(workdir) / args.remote_rel_path
        if not src.exists():
            raise ExperimentError(f"Remote file not found: {src}")
        size = src.stat().st_size
        if size > MAX_DOWNLOAD_BYTES:
            raise ExperimentError(
                f"File {src} is {size / 1e6:.1f} MB > 500 MB limit; keep big data remote."
            )
        import shutil

        local_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, local_dest)
        return {"ok": True, "bytes": size}
    assert host and key
    remote_path = f"{workdir}/{args.remote_rel_path}"
    size_result = subprocess.run(
        _ssh_cmd(host, key, f"stat -c%s {remote_path}"),
        capture_output=True,
        text=True,
        check=False,
    )
    if size_result.returncode != 0:
        raise ExperimentError(f"Could not stat remote file: {size_result.stderr}")
    try:
        size = int(size_result.stdout.strip())
    except ValueError:
        raise ExperimentError(f"Unexpected stat output: {size_result.stdout!r}") from None
    if size > MAX_DOWNLOAD_BYTES:
        raise ExperimentError(
            f"Remote file is {size / 1e6:.1f} MB > 500 MB limit; keep big data remote."
        )
    local_dest.parent.mkdir(parents=True, exist_ok=True)
    dl_result = subprocess.run(
        [
            "scp",
            "-i",
            key,
            "-o",
            "StrictHostKeyChecking=no",
            f"{host}:{remote_path}",
            str(local_dest),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if dl_result.returncode != 0:
        raise ExperimentError(f"scp download failed: {dl_result.stderr}")
    return {"ok": True, "bytes": size}


def exp_tail(args: ExpTailArgs) -> dict:
    """Tail a log file on a target (non-blocking)."""
    kind, workdir, host, key = _resolve_workdir(args.target_id)
    rel = args.rel_log_path
    n = args.lines

    if kind == "local":
        log_path = Path(workdir) / rel
        if not log_path.exists():
            return {"lines": "", "exists": False}
        result = subprocess.run(
            ["tail", "-n", str(n), str(log_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        return {"lines": result.stdout, "exists": True}
    assert host and key
    remote_path = f"{workdir}/{rel}"
    result = subprocess.run(
        _ssh_cmd(host, key, f"tail -n {n} {remote_path} 2>/dev/null || echo ''"),
        capture_output=True,
        text=True,
        check=False,
    )
    return {"lines": result.stdout, "exists": True}


def query_gpus(args: QueryGpusArgs) -> list[dict]:
    """Query free GPU memory on a target."""
    kind, _workdir, host, key = _resolve_workdir(args.target_id)
    nvidia_cmd = "nvidia-smi --query-gpu=memory.total,memory.free --format=csv,noheader,nounits"

    if kind == "local":
        result = subprocess.run(
            nvidia_cmd.split(),
            capture_output=True,
            text=True,
            check=False,
        )
        output = result.stdout
    else:
        assert host and key
        result = subprocess.run(
            _ssh_cmd(host, key, nvidia_cmd),
            capture_output=True,
            text=True,
            check=False,
        )
        output = result.stdout

    gpus: list[dict] = []
    for i, raw in enumerate(output.strip().splitlines()):
        line = raw.strip()
        if line:
            try:
                parts = [part.strip() for part in line.split(",")]
                if len(parts) == 1:
                    free_mb = int(parts[0])
                    gpus.append({"id": i, "free_mb": free_mb})
                else:
                    total_mb = int(parts[0])
                    free_mb = int(parts[1])
                    gpus.append(
                        {
                            "id": i,
                            "total_mb": total_mb,
                            "free_mb": free_mb,
                            "used_mb": max(0, total_mb - free_mb),
                        }
                    )
            except ValueError:
                logger.warning("Unexpected nvidia-smi output line: %r", line)
    return gpus


# ---------------------------------------------------------------------------
# Project-level queue scheduler
# ---------------------------------------------------------------------------


def _scheduler(project_port: int | None = None) -> ExperimentScheduler:
    return ExperimentScheduler(project_port=project_port)


def _queue_unit(args: ExpQueueUnitArgs) -> QueueUnit:
    return QueueUnit(
        cmd=args.cmd,
        target_id=args.target_id,
        gpu_ids=args.gpu_ids,
        gpus_needed=args.gpus_needed,
        min_free_mb=args.min_free_mb,
        reserve_mb=args.reserve_mb,
        priority=args.priority,
        max_retries=args.max_retries,
        metadata=args.metadata,
    )


def exp_queue_submit(args: ExpQueueSubmitArgs) -> dict:
    """Append experiment units to the project-global queue and optionally reconcile.

    Batches are labels for reporting only. Pending units from all batches share
    one fleet-wide pool, so new work merges naturally with already-running
    batches and flows to any allowed GPU that frees up.
    """
    sched = _scheduler(args.project_port)
    return sched.submit(
        [_queue_unit(unit) for unit in args.units],
        requester=args.requester,
        batch_id=args.batch_id,
        metadata=args.metadata,
        reconcile=args.reconcile,
    )


def exp_queue_reconcile(args: ExpQueueReconcileArgs) -> dict:
    """Run one Python-side scheduling pass for all active experiment batches."""
    return _scheduler(args.project_port).reconcile(batch_id=args.batch_id)


def _stale_reconcile_seconds() -> int:
    """How long without a reconcile before ``status`` auto-fires one.

    Defaults to ``experiment_reconcile_interval_seconds`` (the same cadence
    the daemon uses), so operator-mode and daemon-mode converge to the
    same effective freshness. Falls back to 30 s if config can't load —
    safer to over-reconcile than to silently stall.
    """
    try:
        from minions.config import load_gru_config

        return int(load_gru_config().experiment_reconcile_interval_seconds)
    except Exception:
        return 30


def _is_stale(last_iso: str | None, *, max_age_seconds: int) -> bool:
    """True when *last_iso* is missing, malformed, or older than the cap."""
    if not last_iso:
        return True
    try:
        from datetime import UTC, datetime

        last = datetime.fromisoformat(last_iso.replace("Z", "+00:00"))
        return (datetime.now(tz=UTC) - last).total_seconds() > max_age_seconds
    except (ValueError, TypeError):
        return True


def exp_queue_status(args: ExpQueueStatusArgs) -> dict:
    """Return queue status for one batch or the whole project.

    Issue #25: when the project is driven entirely from the MCP surface
    (operator mode — no ``./gru`` daemon supervising the queue), the
    background reconcile loop never runs and pending units silently
    stall. To make operator-mode and daemon-mode equivalent control
    planes, this tool runs a reconcile pass before reading status when
    (a) there are pending units AND (b) the last reconcile is older
    than ``experiment_reconcile_interval_seconds``. The return payload
    includes ``last_reconcile_at`` and ``gpu_idle_warning`` so the caller
    can see *why* the queue advanced (or didn't).
    """
    sched = _scheduler(args.project_port)
    pre = sched.status(batch_id=args.batch_id)
    pending = int(pre.get("summary", {}).get("pending", 0))
    if pending and _is_stale(
        pre.get("last_reconcile_at"),
        max_age_seconds=_stale_reconcile_seconds(),
    ):
        try:
            sched.reconcile(batch_id=args.batch_id)
        except Exception as exc:
            logger.warning(
                "exp_queue_status auto-reconcile failed (port=%s): %s",
                args.project_port,
                exc,
            )
        return sched.status(batch_id=args.batch_id)
    return pre


def exp_gpu_pool_set(args: ExpQueueGpuPoolSetArgs) -> dict:
    """Change which physical GPUs are available for new scheduled runs.

    By default all GPUs are allowed. Passing a concrete list such as
    ``[0, 1, 2, 3]`` makes other GPUs drain-only: running jobs may finish, but
    no new queued units will be placed there.

    Set ``evict=True`` to immediately SIGTERM runs on the removed GPUs and
    requeue their units onto the remaining allowed GPUs. The user's command
    should trap SIGTERM to checkpoint weights before exit.
    """
    return _scheduler(args.project_port).set_gpu_pool(
        target_id=args.target_id,
        allowed_gpu_ids=args.allowed_gpu_ids,
        draining=args.draining,
        evict=args.evict,
        reason=args.reason,
        reconcile=args.reconcile,
    )


def exp_gpu_pool_get(args: ExpQueueGpuPoolGetArgs) -> dict:
    """Return dynamic GPU pool overrides for the project scheduler."""
    return _scheduler(args.project_port).gpu_pool()


def exp_queue_plan(args: ExpQueuePlanArgs) -> dict:
    """Dry-run a candidate submission against the live GPU snapshot.

    Returns the placement decision the scheduler would make right now for
    each unit, plus the snapshot it used. Read-only: nothing is queued and
    no run is launched. Use this to sanity-check before
    ``exp_queue_submit`` — e.g. to confirm 8 sweep units actually spread
    across the fleet instead of piling on one GPU.
    """
    return _scheduler(args.project_port).plan([_queue_unit(u) for u in args.units])
