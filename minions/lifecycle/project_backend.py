"""EACN3 backend process management for MinionsOS projects.

Handles starting, stopping, health checking, and respawning of per-project
EACN3 uvicorn backend subprocesses.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

import httpx

from minions.errors import BackendError
from minions.lifecycle import eacn_client
from minions.lifecycle.eacn_identity import upsert_agent_identity
from minions.paths import MINIONS_ROOT, project_backend_log, project_eacn_db

logger = logging.getLogger(__name__)

HEALTH_TIMEOUT = 20.0  # seconds to wait for backend /health
HEALTH_POLL_INTERVAL = 0.5  # seconds between health probes
EACN_APP = "eacn.network.api.app:create_app"


def port_is_free(port: int) -> bool:
    """Return True if *port* can be bound right now."""
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


def start_backend(port: int) -> subprocess.Popen:  # type: ignore[type-arg]
    """Start the EACN3 uvicorn backend subprocess for *port*.

    Pre-checks port availability. Raises BackendError if occupied.
    Logs go to project_{port}/logs/backend.log.
    """
    if not port_is_free(port):
        # Check if the occupying process is a foreign (non-MinionsOS) backend
        pids = backend_listener_pids(port)
        for pid in pids:
            if not is_minions_backend_pid(pid, port):
                raise BackendError(
                    f"Port {port} is held by foreign process PID={pid} "
                    f"(command: {pid_command(pid)[:80]}). Refusing to start."
                )
        raise BackendError(f"Port {port} is already occupied. Cannot start backend.")

    db_path = str(project_eacn_db(port))
    log_path = project_backend_log(port)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    project_eacn_db(port).parent.mkdir(parents=True, exist_ok=True)

    env = {**os.environ, "EACN3_DB_PATH": db_path}
    log_fp = log_path.open("a", encoding="utf-8")

    cmd = [
        "uvicorn",
        EACN_APP,
        "--factory",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    logger.info("Starting EACN3 backend on port %d: %s", port, " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=log_fp,
        stderr=log_fp,
        cwd=str(MINIONS_ROOT),
    )
    logger.debug("Backend PID=%d for port %d", proc.pid, port)
    return proc


def wait_for_health(port: int, timeout: float = HEALTH_TIMEOUT) -> None:
    """Poll /health until the backend responds 200 or *timeout* expires.

    Raises BackendError on timeout.
    """
    url = f"http://127.0.0.1:{port}/health"
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(url, timeout=2.0)
            if resp.status_code == 200:
                logger.info("Backend on port %d is healthy.", port)
                return
        except Exception as exc:
            last_exc = exc
        time.sleep(HEALTH_POLL_INTERVAL)
    raise BackendError(
        f"Backend on port {port} did not become healthy within {timeout}s. Last error: {last_exc}"
    )


def register_server(port: int) -> tuple[str, str]:
    """Register a MinionsOS server record with the EACN3 backend."""
    return eacn_client.register_server(port)


def ensure_local_balance(port: int, agent_id: str) -> None:
    """Best-effort local EACN credit seeding for MinionsOS project agents."""
    try:
        from minions.config import load_gru_config

        minimum = load_gru_config().local_eacn_initial_balance
        eacn_client.ensure_balance(port, agent_id, minimum)
    except Exception as exc:
        logger.warning(
            "Could not seed local EACN balance for agent=%s port=%d: %s",
            agent_id,
            port,
            exc,
        )


def pid_alive(pid: int) -> bool:
    """Check if a process is alive."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def backend_listener_pids(port: int) -> list[int]:
    """Return PIDs listening on *port*, best effort.

    This is used only as a fallback when meta.json has a missing/stale
    backend PID. Keep it conservative: callers still verify the command line
    before killing a discovered process.
    """
    try:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return []
    if result.returncode not in {0, 1}:
        return []
    pids: list[int] = []
    for line in result.stdout.splitlines():
        try:
            pids.append(int(line.strip()))
        except ValueError:
            continue
    return list(dict.fromkeys(pids))


def pid_command(pid: int) -> str:
    """Get the command line for a process."""
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def is_minions_backend_pid(pid: int, port: int) -> bool:
    """Return True when process metadata matches this project's EACN backend."""
    command = pid_command(pid)
    return "uvicorn" in command and EACN_APP in command and str(port) in command


def terminate_backend_pid(port: int, pid: int) -> None:
    """Terminate a backend process gracefully."""
    try:
        import signal

        os.kill(pid, signal.SIGTERM)
        # Give it a moment to shut down.
        for _ in range(20):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            os.kill(pid, signal.SIGKILL)
        logger.info("Stopped backend PID=%d (port %d).", pid, port)
    except ProcessLookupError:
        logger.debug("Backend PID=%d already gone.", pid)
    except Exception as exc:
        logger.warning("Error stopping backend PID=%d: %s", pid, exc)


def stop_backend(port: int, pid: int | None) -> bool:
    """Terminate the backend process for *port* gracefully.

    Returns True if the backend port is free afterwards. If the recorded PID is
    missing or stale, fall back to the listener on the project port, but only
    kill a discovered process whose command line matches MinionsOS' uvicorn
    backend.

    GitHub Issue #23: when the recorded PID is already dead and the port is
    free, port_is_free can briefly return False on the first poll due to
    a TIME_WAIT / closing-socket window. We retry the port check for up to
    1 s in 100 ms increments before falling back to listener discovery, so a
    stale-PID stop is idempotent on the first call.
    """
    if pid is not None:
        terminate_backend_pid(port, pid)
        for _ in range(10):
            if port_is_free(port):
                return True
            time.sleep(0.1)

    for _ in range(10):
        if port_is_free(port):
            return True
        time.sleep(0.1)

    fallback_pids = [p for p in backend_listener_pids(port) if p != pid]
    for fallback_pid in fallback_pids:
        if not is_minions_backend_pid(fallback_pid, port):
            logger.warning(
                "Refusing to stop unverified listener PID=%d on port %d; command=%r",
                fallback_pid,
                port,
                pid_command(fallback_pid),
            )
            continue
        logger.info(
            "Stopping backend listener PID=%d discovered on port %d after stale/missing meta PID.",
            fallback_pid,
            port,
        )
        terminate_backend_pid(port, fallback_pid)
        for _ in range(10):
            if port_is_free(port):
                return True
            time.sleep(0.1)

    logger.warning("Backend on port %d is still listening after stop attempt.", port)
    return False


def respawn_backend(port: int) -> None:
    """Respawn the EACN3 backend for *port* after a crash.

    Called by gru.loop when backend health check fails but crash threshold
    not yet exceeded. Stops any stale backend process, starts a fresh one,
    waits for /health, and re-registers the server.

    Raises BackendError if respawn fails.
    """
    # Stop any existing backend process
    pids = backend_listener_pids(port)
    for pid in pids:
        if is_minions_backend_pid(pid, port):
            terminate_backend_pid(port, pid)
            time.sleep(0.5)

    # Verify port is free
    if not port_is_free(port):
        raise BackendError(f"Port {port} still occupied after stop; cannot respawn.")

    # Start fresh backend
    proc = start_backend(port)
    logger.info("Backend respawned on port %d (PID=%d).", port, proc.pid)

    # Wait for health
    wait_for_health(port)

    # Re-register server (updates server_id and token)
    try:
        server_id, _token = register_server(port)
        logger.info("Backend re-registered: server_id=%s", server_id)
    except Exception as exc:
        logger.warning("Backend respawn succeeded but re-registration failed: %s", exc)


class AdoptedBackend:
    """Small proc-like wrapper for a backend already running on the project port."""

    def __init__(self, pid: int) -> None:
        self.pid = pid

    def terminate(self) -> None:
        # This process predates revive; leave it running if a later revive step
        # fails so the operator can inspect/repair without another side effect.
        return None


def adopt_running_backend(port: int) -> AdoptedBackend | None:
    """Return an existing MinionsOS backend for *port*, if safely identifiable."""
    try:
        resp = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2.0)
        if resp.status_code != 200:
            return None
    except Exception:
        return None

    for pid in backend_listener_pids(port):
        if is_minions_backend_pid(pid, port):
            logger.info("Adopting already-running backend PID=%d on port %d.", pid, port)
            return AdoptedBackend(pid)
    return None


def gru_agent_spec() -> tuple[str, list[str], str]:
    """Return the EACN agent spec for Gru."""
    from minions.config import load_gru_config

    gru_agent_id = load_gru_config().gru_eacn_agent_id
    gru_domains = ["minionsos", "project-local", "role:gru", "coordination"]
    gru_description = (
        "MinionsOS global coordinator EACN queue on this project. "
        "Drained by Gru's resident agent through mos_await_events."
    )
    return gru_agent_id, gru_domains, gru_description


def register_gru_eacn_agent(port: int, server_id: str) -> tuple[str, str]:
    """Register the Gru EACN agent on a project backend."""
    gru_agent_id, gru_domains, gru_description = gru_agent_spec()
    gru_agent_token, _seeds = eacn_client.register_agent(
        port=port,
        agent_id=gru_agent_id,
        name="gru",
        server_id=server_id,
        domains=gru_domains,
        description=gru_description,
        tier="coordinator",
    )
    ensure_local_balance(port, gru_agent_id)
    upsert_agent_identity(
        port,
        role_name="gru",
        agent_id=gru_agent_id,
        kind="gru_mailbox",
        server_id=server_id,
        agent_token=gru_agent_token,
        domains=gru_domains,
        tier="coordinator",
        description=gru_description,
        name="gru",
    )
    return gru_agent_id, gru_agent_token
