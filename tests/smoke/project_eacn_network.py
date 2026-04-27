"""Smoke test: every project agent joins the project-local EACN3 network.

Usage:
    uv run python tests/smoke/project_eacn_network.py

This creates a temporary parent git repo, creates one fictional MinionsOS project,
registers Noter/Coder/Expert roles, and verifies:
- Gru, Noter, Coder, and Expert all appear in EACN discovery for that project.
- Gru -> Noter initial task, Coder -> Gru, Coder -> Expert, and Expert -> Coder
  messages are all delivered through the project's local EACN3 queue.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

FAILURES: list[str] = []


def step(name: str, ok: bool, detail: str = "") -> None:
    mark = "✓" if ok else "✗"
    line = f"  {mark} {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    if not ok:
        FAILURES.append(name)


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed: {result.stderr}")
    return result


def event_payloads(resp: dict[str, Any]) -> list[dict[str, Any]]:
    events = resp.get("events") or []
    return [e.get("payload", {}) for e in events if isinstance(e, dict)]


def has_content(resp: dict[str, Any], expected: dict[str, Any]) -> bool:
    return any(payload.get("content") == expected for payload in event_payloads(resp))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="minionsos-eacn-smoke-")).resolve()
    print(f"[eacn-smoke] tmp = {tmp}")

    root = tmp / "minionsos"
    root.mkdir()
    os.environ["MINIONS_ROOT"] = str(root)

    run(["git", "init", "-q", "-b", "main"], cwd=tmp)
    run(["git", "config", "user.email", "eacn-smoke@test"], cwd=tmp)
    run(["git", "config", "user.name", "eacn-smoke"], cwd=tmp)
    (tmp / "README.md").write_text("fictional project eacn smoke\n", encoding="utf-8")
    run(["git", "add", "."], cwd=tmp)
    run(["git", "commit", "-q", "-m", "init"], cwd=tmp)

    for mod in list(sys.modules):
        if mod == "minions" or mod.startswith("minions."):
            del sys.modules[mod]

    from minions.lifecycle import eacn_client, gru_inbox
    from minions.lifecycle.project import project_close, project_create, project_meta_json
    from minions.lifecycle.role import list_roles, register_expert, register_role
    from minions.lifecycle.wakeup import WakeupScheduler
    from minions.paths import MINIONS_ROOT
    from minions.state.store import StateStore
    from minions.tools.mcp_server import GruInboxPollArgs, gru_inbox_poll

    assert root == MINIONS_ROOT, f"MINIONS_ROOT mismatch: {MINIONS_ROOT}"

    port: int | None = None
    try:
        print("[eacn-smoke] create fictional project")
        project = project_create(
            real_name="Fictional Project Local EACN Test",
            venue="Imaginary Systems 2026",
            base_branch="HEAD",
            brief="A throwaway project used only to test project-local EACN behavior.",
        )
        port = project.port
        meta = json.loads(project_meta_json(port).read_text(encoding="utf-8"))
        step("project created", project.status == "active", f"port={port}")
        step("project has eacn server id", bool(meta.get("eacn3_server_id")))

        print("[eacn-smoke] register project roles")
        noter_init_brief = "Observe this fictional project through project-local EACN only."
        noter = register_role(
            port,
            "noter",
            init_brief=noter_init_brief,
            poll_interval="1m",
        )
        coder = register_role(port, "coder", poll_interval="1m")
        expert = register_expert(
            port,
            "Deep Learning Architecture",
            init_brief=None,
            poll_interval="1m",
        )
        role_ids = {noter["eacn_agent_id"], coder["eacn_agent_id"], expert["eacn_agent_id"]}
        expected_agents = {"gru", *role_ids}

        snap = eacn_client.probe_backend(port)
        discovered = {a.get("agent_id") for a in snap.get("agents", [])}
        step(
            "Gru/Noter/Coder/Expert are EACN AgentCards",
            expected_agents <= discovered,
            f"expected={sorted(expected_agents)} discovered={sorted(discovered)}",
        )

        roles = list_roles(port)
        listed_ids = {r["eacn_agent_id"] for r in roles}
        step("role registry stores eacn ids", role_ids <= listed_ids, f"ids={sorted(listed_ids)}")

        print("[eacn-smoke] verify project-local message delivery")
        noter_init = eacn_client.poll_events(port, "noter", timeout_secs=1)
        step(
            "Gru -> Noter init_brief direct message delivered through EACN",
            has_content(
                noter_init,
                {
                    "type": "init_brief",
                    "description": noter_init_brief,
                    "role": "noter",
                },
            ),
            f"count={noter_init.get('count')}",
        )

        eacn_client.post_message(
            port=port,
            to_agent_id="gru",
            from_agent_id="coder",
            content={"kind": "status", "text": "Coder reports via project-local EACN."},
        )
        polled = gru_inbox_poll(GruInboxPollArgs(port=port))
        drained = polled["polled"]
        gru_entries = gru_inbox.read_unread(port, max_events=10)
        step(
            "Coder -> Gru queue delivered through EACN",
            drained >= 1
            and any(
                entry.get("event", {}).get("payload", {}).get("from") == "coder"
                for entry in gru_entries
            ),
            f"drained={drained} unread={len(gru_entries)}",
        )

        expert_id = str(expert["eacn_agent_id"])
        coder_to_expert = {"kind": "handoff", "text": "Please inspect this fake architecture."}
        eacn_client.post_message(
            port=port,
            to_agent_id=expert_id,
            from_agent_id="coder",
            content=coder_to_expert,
        )
        expert_events = eacn_client.poll_events(port, expert_id, timeout_secs=1)
        step(
            "Coder -> Expert delivered through EACN",
            has_content(expert_events, coder_to_expert),
            f"count={expert_events.get('count')}",
        )

        expert_to_coder = {"kind": "reply", "text": "Expert reply over the same local EACN."}
        eacn_client.post_message(
            port=port,
            to_agent_id="coder",
            from_agent_id=expert_id,
            content=expert_to_coder,
        )

        calls: list[tuple[str, int, list[dict[str, Any]]]] = []

        def fake_invoke(
            role_name: str,
            project_port: int,
            events: list[dict[str, Any]],
            **_: Any,
        ) -> None:
            calls.append((role_name, project_port, events))

        scheduler = WakeupScheduler(
            store=StateStore(),
            invoke_fn=fake_invoke,
            cooldown_seconds=0,
        )
        triggered = asyncio.run(scheduler.tick_once())
        step(
            "Expert -> Coder triggers role wakeup from EACN event",
            triggered >= 1 and any(call[0] == "coder" for call in calls),
            f"triggered={triggered} calls={[c[0] for c in calls]}",
        )

        project_close(port)
        port = None
    finally:
        if port is not None:
            with contextlib.suppress(Exception):
                project_close(port)
        print(f"[eacn-smoke] cleaning up {tmp}")
        shutil.rmtree(tmp, ignore_errors=True)

    if FAILURES:
        print(f"\n[eacn-smoke] FAILED: {len(FAILURES)} step(s): {FAILURES}")
        return 1
    print("\n[eacn-smoke] ALL STEPS PASSED ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
