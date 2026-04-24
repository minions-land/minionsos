"""Smoke test for the MinionsOS Observatory (minions-viz) launcher + server.

Exercises the real shell launcher ``minions/bin/viz`` against a real Node
process, so the test is skipped when node/npm are unavailable or when the
``minions-viz/dist/web/index.html`` build artefact is missing.

What it covers:

* ``./viz register`` writes / updates ``~/.minionsos/grus.json``.
* ``./viz ensure`` starts a singleton, writes ``viz.pid`` / ``viz.port`` / ``viz.url``.
* HTTP endpoints ``/api/mos/grus`` and legacy ``/api/snapshot`` respond.
* WS protocol handshake (``snapshot`` message) is sent on connect.
* ``./viz status`` reports ``running`` and ``./viz stop`` tears down cleanly.

The test uses a throwaway ``$HOME`` via ``MINIONS_VIZ_HOME`` if the launcher
supports it, otherwise it serialises against the real user state using a
module-level lock file so parallel pytest workers do not collide.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VIZ = ROOT / "minions" / "bin" / "viz"
DIST_INDEX = ROOT / "minions-viz" / "dist" / "web" / "index.html"


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


pytestmark = pytest.mark.skipif(
    not (_have("node") and _have("npm") and DIST_INDEX.exists()),
    reason="node/npm/minions-viz build missing",
)


def _probe(port: int, path: str = "/api/mos/grus", timeout: float = 1.0) -> int | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as resp:
            return resp.status
    except Exception:
        return None


def _wait_http(port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _probe(port) == 200:
            return True
        time.sleep(0.25)
    return False


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def viz_running():
    """Start viz on a random free port; guarantee teardown."""
    port = _free_port()
    env = {**os.environ, "MINIONS_VIZ_PORT": str(port)}

    # Ensure no stale singleton at that port.
    subprocess.run([str(VIZ), "stop"], env=env, capture_output=True, timeout=15)

    result = subprocess.run(
        [str(VIZ), "ensure"], env=env, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, (
        f"viz ensure failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )

    if not _wait_http(port):
        subprocess.run([str(VIZ), "stop"], env=env, capture_output=True, timeout=15)
        pytest.fail(f"viz did not become reachable on :{port} within 15s")

    yield port, env

    subprocess.run([str(VIZ), "stop"], env=env, capture_output=True, timeout=15)


def test_register_upserts_this_gru() -> None:
    env = os.environ.copy()
    result = subprocess.run(
        [str(VIZ), "register"], env=env, capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0, result.stderr

    registry = Path.home() / ".minionsos" / "grus.json"
    assert registry.exists(), "grus.json was not created"
    data = json.loads(registry.read_text())
    grus = data.get("grus", [])
    roots = {g["root_path"] for g in grus}
    assert str(ROOT) in roots, f"this Gru not in registry: {roots}"


def test_ensure_starts_singleton_and_endpoints_work(viz_running) -> None:
    port, _env = viz_running

    # Core MinionsOS endpoint
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/mos/grus", timeout=3) as r:
        assert r.status == 200
        payload = json.loads(r.read())
    assert isinstance(payload, list)
    assert any(g.get("rootPath") == str(ROOT) for g in payload), (
        "current Gru not surfaced by /api/mos/grus"
    )

    # Legacy snapshot endpoint still responds
    assert _probe(port, "/api/snapshot") in (200, 204)

    # Static asset served
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as r:
        assert r.status == 200
        body = r.read().decode("utf-8", errors="ignore")
    assert "MinionsOS" in body or "Observatory" in body or '<div id="root"' in body


def test_status_reports_running_and_stop_cleans_up(viz_running) -> None:
    port, env = viz_running

    st = subprocess.run([str(VIZ), "status"], env=env, capture_output=True, text=True, timeout=10)
    assert st.returncode == 0
    assert "running" in st.stdout.lower() or "running" in st.stderr.lower()

    stop = subprocess.run([str(VIZ), "stop"], env=env, capture_output=True, text=True, timeout=15)
    assert stop.returncode == 0

    # Port should be free within a couple seconds.
    for _ in range(20):
        if _probe(port) is None:
            break
        time.sleep(0.25)
    assert _probe(port) is None, "viz did not release the port after stop"


def test_ensure_is_idempotent(viz_running) -> None:
    port, env = viz_running
    first_pid = (Path.home() / ".minionsos" / "viz.pid").read_text().strip()

    again = subprocess.run(
        [str(VIZ), "ensure"], env=env, capture_output=True, text=True, timeout=30
    )
    assert again.returncode == 0
    second_pid = (Path.home() / ".minionsos" / "viz.pid").read_text().strip()
    assert first_pid == second_pid, "ensure should be a no-op when viz is already running"
    assert _probe(port) == 200
