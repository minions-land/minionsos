"""Experiment execution MCP tools for the Experimenter role.

These tools are only loaded when the role is ``experimenter`` (whitelisting
is enforced at spawn time via ``--allowed-tools``).

All execution is **fire-and-poll**: ``exp_run`` launches the command fully
detached via ``nohup``/``setsid`` and returns immediately with a ``run_id``.
Use ``exp_status``/``exp_wait``/``exp_list`` to observe progress and
``exp_kill`` to terminate.

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
"""
from __future__ import annotations

import json
import logging
import shlex
import subprocess
import time
import uuid
from pathlib import Path
from typing import Literal

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from minions.config import load_experiment_targets
from minions.errors import ConfigError, ExperimentError

logger = logging.getLogger(__name__)

mcp = FastMCP("minions-exp")

# ---------------------------------------------------------------------------
# Size limit
# ---------------------------------------------------------------------------

MAX_DOWNLOAD_BYTES = 500 * 1024 * 1024  # 500 MB

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _expand_workdir(workdir: str) -> str:
    """Expand template tokens in a target's ``workdir`` string.

    Supported tokens:
    - ``{project_workspace}`` → absolute path of the current project's git
      worktree (``project_{port}/workspace``), resolved from the
      ``MINIONS_PROJECT_PORT`` env var. Falls back to the literal token
      if the env var is absent (e.g. standalone CLI use).
    """
    import os

    if "{project_workspace}" in workdir:
        port_s = os.environ.get("MINIONS_PROJECT_PORT")
        if port_s and port_s.isdigit():
            from minions.paths import project_workspace as _pws

            workdir = workdir.replace(
                "{project_workspace}", str(_pws(int(port_s)).resolve())
            )
    return workdir


def _resolve_workdir(
    target_id: str,
) -> tuple[Literal["local", "ssh"], str, str | None, str | None]:
    """Return (type, workdir, host, key) for *target_id*."""
    cfg = load_experiment_targets()
    target = cfg.get_target(target_id)
    workdir = _expand_workdir(target.workdir)
    if target.type == "local":
        return "local", workdir, None, None
    return "ssh", workdir, target.host, target.key  # type: ignore[return-value]


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
    if not cfg.targets:
        raise ConfigError("No experiment targets configured.")
    return cfg.targets[0].id


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


def _build_launch_script(cmd: str, workdir: str, log_path: str, exit_path: str) -> str:
    """Build the nohup/setsid detached launcher.

    Runs the user cmd in a subshell, captures its exit code into ``exit_path``
    after it terminates, and echoes the child PID on stdout. ``setsid`` is
    used when present to fully detach from the controlling terminal; when
    absent (e.g. macOS default install) ``nohup`` + ``disown`` is sufficient.
    """
    inner = (
        f"cd {shlex.quote(workdir)} && "
        f"( {cmd} ); echo $? > {shlex.quote(exit_path)}"
    )
    # Prefer setsid for full session detachment, but fall back gracefully.
    detach = (
        "if command -v setsid >/dev/null 2>&1; then DETACH=setsid; else DETACH=; fi; "
    )
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
    timeout: int | None = Field(
        default=None,
        description="DEPRECATED: no-op. exp_run is always non-blocking; use exp_wait(timeout=...).",
    )
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


# ---------------------------------------------------------------------------
# exp_run — fire-and-poll
# ---------------------------------------------------------------------------


@mcp.tool()
def exp_run(args: ExpRunArgs) -> dict:
    """Launch a command **detached** on a local or SSH target, return immediately.

    Returns ``{run_id, pid, log_path, target_id}``. The command runs under
    ``nohup setsid`` so closing the SSH session or the calling agent does
    not kill it. Use ``exp_status`` / ``exp_wait`` to observe progress.

    The legacy ``timeout`` parameter is a no-op (kept for backwards call
    compatibility). Use ``exp_wait(timeout=...)`` instead.
    """
    target_id = _resolve_target_id(args.target_id)
    kind, workdir, host, key = _resolve_workdir(target_id)

    run_id = _new_run_id()
    cmd = args.cmd
    env_prefix = ""
    if args.gpu_ids is not None:
        ids_str = ",".join(str(g) for g in args.gpu_ids)
        env_prefix = f"CUDA_VISIBLE_DEVICES={ids_str} "
    cmd = env_prefix + cmd

    logger.info(
        "exp_run target=%s run_id=%s cmd=%r (detached)", target_id, run_id, cmd[:120]
    )

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
        script = _build_launch_script(cmd, workdir, str(log_path), str(exit_path))
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ExperimentError(
                f"Failed to launch local run {run_id}: {result.stderr}"
            )
        try:
            pid = int(result.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError) as exc:
            raise ExperimentError(
                f"Could not parse launch pid: {result.stdout!r}"
            ) from exc
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
    launch = _build_launch_script(cmd, workdir, log_path_s, exit_path_s)
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
        raise ExperimentError(
            f"Could not parse launch pid: {result.stdout!r}"
        ) from exc
    meta["pid"] = pid
    meta_blob = json.dumps(meta, indent=2)
    # Write meta on the remote side.
    write_meta = (
        f"cat > {shlex.quote(meta_path_s)} <<'__MINIONS_META__'\n"
        f"{meta_blob}\n__MINIONS_META__"
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


def _local_status(workdir: str, run_id: str) -> dict:
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
    return {"state": "running", "log_tail": log_tail}


def _ssh_status(host: str, key: str, workdir: str, run_id: str) -> dict:
    _logs_dir, log_path, meta_path, exit_path = _remote_paths(workdir, run_id)
    check = (
        f"if [ ! -f {shlex.quote(meta_path)} ]; then echo MISSING; exit 0; fi; "
        f"if [ -f {shlex.quote(exit_path)} ]; then "
        f"  echo EXITED; cat {shlex.quote(exit_path)}; "
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
    return {"state": "running", "log_tail": log_tail}


@mcp.tool()
def exp_status(args: ExpStatusArgs) -> dict:
    """Check run state. Returns ``{state, exit_code?, log_tail}``."""
    target_id = _resolve_target_id(args.target_id)
    kind, workdir, host, key = _resolve_workdir(target_id)
    if kind == "local":
        return _local_status(workdir, args.run_id)
    assert host and key
    return _ssh_status(host, key, workdir, args.run_id)


@mcp.tool()
def exp_wait(args: ExpWaitArgs) -> dict:
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


@mcp.tool()
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

            os.kill(pid, signal.SIGTERM)
            return {"killed": True, "pid": pid}
        except ProcessLookupError:
            return {"killed": False, "pid": pid}
    assert host and key
    cmd = (
        f"if [ -f {shlex.quote(meta_path)} ]; then "  # type: ignore[arg-type]
        f"  PID=$(python3 -c \"import json;print(json.load(open('{meta_path}'))['pid'])\"); "
        f"  kill -TERM $PID && echo OK || echo GONE; "
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


@mcp.tool()
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
            }
        )
    return runs


# ---------------------------------------------------------------------------
# exp_put / exp_get / exp_tail / query_gpus (unchanged)
# ---------------------------------------------------------------------------


@mcp.tool()
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


@mcp.tool()
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
        raise ExperimentError(
            f"Unexpected stat output: {size_result.stdout!r}"
        ) from None
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


@mcp.tool()
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


@mcp.tool()
def query_gpus(args: QueryGpusArgs) -> list[dict]:
    """Query free GPU memory on a target."""
    kind, _workdir, host, key = _resolve_workdir(args.target_id)
    nvidia_cmd = "nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits"

    if kind == "local":
        result = subprocess.run(
            nvidia_cmd,
            shell=True,
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
                gpus.append({"id": i, "free_mb": int(line)})
            except ValueError:
                logger.warning("Unexpected nvidia-smi output line: %r", line)
    return gpus
