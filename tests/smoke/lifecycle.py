"""Standalone lifecycle smoke test.

Usage:
    uv run python tests/smoke/lifecycle.py

Exits non-zero on any failure; prints ✓/✗ per step.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

FAILURES: list[str] = []


def step(name: str, ok: bool, detail: str = "") -> None:
    mark = "✓" if ok else "✗"
    line = f"  {mark} {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    if not ok:
        FAILURES.append(name)


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed: {r.stderr}")
    return r


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="minionsos-smoke-")).resolve()
    print(f"[smoke] tmp = {tmp}")

    # Layout: tmp/ is git repo; tmp/minionsos/ is MINIONS_ROOT.
    root = tmp / "minionsos"
    root.mkdir()
    os.environ["MINIONS_ROOT"] = str(root)

    # Git init parent repo + initial commit.
    run(["git", "init", "-q", "-b", "main"], cwd=tmp)
    run(["git", "config", "user.email", "smoke@test"], cwd=tmp)
    run(["git", "config", "user.name", "smoke"], cwd=tmp)
    (tmp / "README.md").write_text("smoke\n")
    run(["git", "add", "."], cwd=tmp)
    run(["git", "commit", "-q", "-m", "init"], cwd=tmp)

    # Import AFTER env is set so minions.paths picks up MINIONS_ROOT.
    # Force reimport in case cached.
    for mod in list(sys.modules):
        if mod == "minions" or mod.startswith("minions."):
            del sys.modules[mod]

    from minions.lifecycle import eacn_client
    from minions.lifecycle.project import (
        project_close,
        project_create,
        project_dormant,
        project_revive,
    )
    from minions.paths import MINIONS_ROOT, PROJECTS_JSON, project_dir, project_meta_json

    assert root == MINIONS_ROOT, f"MINIONS_ROOT mismatch: {MINIONS_ROOT}"

    port: int | None = None
    try:
        # Step 3: project_create
        print("[smoke] step 3: project_create")
        entry = project_create("smoke-test", base_branch="HEAD")
        port = entry.port
        step("project_create returns ProjectEntry", entry.status == "active")

        # Step 4: backend health, meta.json, worktree, projects.json
        print("[smoke] step 4: health / meta / worktree / state")
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=3)
            step("GET /health == 200", r.status_code == 200, f"code={r.status_code}")
        except Exception as exc:
            step("GET /health == 200", False, str(exc))

        meta_path = project_meta_json(port)
        step("meta.json exists", meta_path.exists())
        meta = json.loads(meta_path.read_text())
        step(
            "meta.json has port/status/server_id/server_token",
            meta.get("port") == port
            and meta.get("status") == "active"
            and "eacn3_server_id" in meta
            and "eacn3_server_token" in meta,
        )

        ws = project_dir(port) / "workspace"
        step("worktree dir exists with .git", ws.exists() and (ws / ".git").exists())

        projects_data = json.loads(PROJECTS_JSON.read_text())
        step(
            "projects.json has entry",
            any(p["port"] == port for p in projects_data["projects"]),
        )

        # Step 5: register a fake agent via eacn_client
        print("[smoke] step 5: register_agent")
        try:
            agent_id = f"test@{port}"
            server_id = meta["eacn3_server_id"]
            _token, seeds = eacn_client.register_agent(
                port=port,
                agent_id=agent_id,
                name="test",
                server_id=server_id,
                domains=["coordination"],
                skills=[{"name": "test", "description": "test", "parameters": {}}],
            )
            step("register_agent returned token", True, f"seeds={len(seeds)}")
        except Exception as exc:
            step("register_agent returned token", False, str(exc))
            agent_id = None

        # Step 6: send self-message and poll
        if agent_id:
            print("[smoke] step 6: post_message + poll_events")
            try:
                eacn_client.post_message(
                    port=port,
                    to_agent_id=agent_id,
                    from_agent_id=agent_id,
                    content={"hello": "world"},
                )
                # Poll (drain buffered).
                got = None
                for _ in range(5):
                    resp = eacn_client.poll_events(port, agent_id, timeout_secs=1)
                    if resp.get("count", 0) > 0:
                        got = resp
                        break
                    time.sleep(0.2)
                ok = bool(got and got["count"] >= 1)
                step("poll_events received message", ok, f"resp={got}")
            except Exception as exc:
                step("poll_events received message", False, str(exc))

        # Step 7: dormant
        print("[smoke] step 7: project_dormant")
        project_dormant(port)
        time.sleep(0.5)
        down = False
        try:
            httpx.get(f"http://127.0.0.1:{port}/health", timeout=1.0)
        except Exception:
            down = True
        step("backend is down after dormant", down)
        meta2 = json.loads(project_meta_json(port).read_text())
        step("meta.json status=dormant", meta2.get("status") == "dormant")

        tags = run(["git", "tag"], cwd=tmp).stdout.splitlines()
        step(
            "dormant git tag exists",
            any(t.startswith(f"minionsos/dormant/project-{port}") for t in tags),
        )

        # Step 8: revive
        print("[smoke] step 8: project_revive")
        project_revive(port)
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=3)
            step("backend healthy after revive", r.status_code == 200)
        except Exception as exc:
            step("backend healthy after revive", False, str(exc))

        # Step 9: close
        print("[smoke] step 9: project_close")
        project_close(port)
        tags = run(["git", "tag"], cwd=tmp).stdout.splitlines()
        step(
            "closed git tag exists",
            f"minionsos/closed/project-{port}" in tags,
        )
        projects_data = json.loads(PROJECTS_JSON.read_text())
        step(
            "port in retired_ports",
            port in projects_data.get("retired_ports", []),
        )

    finally:
        # Best-effort: make sure backend is dead.
        if port is not None:
            try:
                meta = json.loads(project_meta_json(port).read_text())
                pid = meta.get("backend_pid")
                if pid:
                    try:
                        import signal

                        os.kill(pid, signal.SIGKILL)
                    except Exception:
                        pass
            except Exception:
                pass
        print(f"[smoke] cleaning up {tmp}")
        shutil.rmtree(tmp, ignore_errors=True)

    if FAILURES:
        print(f"\n[smoke] FAILED: {len(FAILURES)} step(s): {FAILURES}")
        return 1
    print("\n[smoke] ALL STEPS PASSED ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
