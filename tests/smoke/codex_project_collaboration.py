"""Smoke test: Codex-host project collaboration over EACN3.

Usage:
    uv run python tests/smoke/codex_project_collaboration.py

This creates a temporary parent git repo, configures MinionsOS to use the
Codex agent host, installs a fake ``codex`` binary on PATH, creates one project,
registers several roles, sends project-local EACN tasks/messages, and verifies
that the Python WakeupScheduler launches the roles through ``codex exec -``.

The fake Codex binary avoids live API calls while still exercising the real
MinionsOS role invocation pipeline, environment propagation, subprocess logs,
EACN delivery, and Gru queue polling path.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

FAILURES: list[str] = []

FAKE_CODEX = r"""#!/usr/bin/env bash
set -u
ARGS=("$@")
if [[ "${ARGS[0]:-}" != "exec" ]]; then
  echo "fake-codex: missing exec subcommand" >&2
  exit 2
fi
has_stdin=0
for a in "${ARGS[@]}"; do
  if [[ "$a" == "-" ]]; then has_stdin=1; fi
  if [[ "$a" == "--append-system-prompt" || "$a" == "--allowed-tools" ]]; then
    echo "fake-codex: Claude-only flag $a leaked into codex argv" >&2
    exit 3
  fi
done
if [[ "$has_stdin" -ne 1 ]]; then
  echo "fake-codex: missing stdin prompt marker '-'" >&2
  exit 4
fi
echo "FAKE_CODEX_ARGV: ${ARGS[*]}" >&2
echo "FAKE_CODEX_ROLE: ${MINIONS_ROLE_NAME:-missing}" >&2
echo "FAKE_CODEX_PROJECT: ${MINIONS_PROJECT_PORT:-missing}" >&2
echo "FAKE_CODEX_WAKEUP: ${MINIONS_WAKEUP_CLASS:-missing}" >&2
echo "FAKE_CODEX_STDIN_BEGIN" >&2
cat >&2
echo "" >&2
echo "FAKE_CODEX_STDIN_END" >&2
exit 0
"""


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


def install_fake_codex(tmp: Path) -> Path:
    bindir = tmp / "bin"
    bindir.mkdir()
    codex = bindir / "codex"
    codex.write_text(FAKE_CODEX, encoding="utf-8")
    codex.chmod(codex.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return bindir


def wait_for_log(path: Path, needle: str, timeout: float = 5.0) -> str:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        if path.exists():
            last = path.read_text(encoding="utf-8", errors="replace")
            if needle in last:
                return last
        time.sleep(0.05)
    return last


def contains_payload(resp: dict[str, Any], expected: dict[str, Any]) -> bool:
    events = resp.get("events") or []
    for event in events:
        if not isinstance(event, dict):
            continue
        payload = event.get("payload") or {}
        if payload.get("content") == expected:
            return True
    return False


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="minionsos-codex-collab-")).resolve()
    print(f"[codex-collab] tmp = {tmp}")

    root = tmp / "minionsos"
    root.mkdir()
    bindir = install_fake_codex(tmp)

    os.environ["MINIONS_ROOT"] = str(root)
    os.environ["MINIONS_AGENT_HOST"] = "codex"
    os.environ["PATH"] = f"{bindir}:{os.environ.get('PATH', '')}"

    (root / ".codex").mkdir(parents=True, exist_ok=True)
    (root / ".codex" / "config.toml").write_text(
        "\n".join(
            [
                "[mcp_servers.minionsos]",
                'command = "uv"',
                'args = ["run", "--project", ".", "python", "-m", "minions.tools.mcp_server"]',
                "enabled = true",
                'env = { MINIONS_MCP_PROFILE = "codex" }',
                "",
                "[mcp_servers.eacn3]",
                'command = "uv"',
                'args = ["run", "--project", ".", "python", "-m", '
                '"minions.tools.eacn3_mcp_proxy", "--", "node", '
                '"EACN3/plugin/dist/server.js"]',
                "enabled = true",
                'env = { EACN3_MCP_PROFILE = "codex-core" }',
                "",
            ]
        ),
        encoding="utf-8",
    )

    run(["git", "init", "-q", "-b", "main"], cwd=tmp)
    run(["git", "config", "user.email", "codex-collab@test"], cwd=tmp)
    run(["git", "config", "user.name", "codex-collab"], cwd=tmp)
    (tmp / "README.md").write_text("codex collaboration smoke\n", encoding="utf-8")
    run(["git", "add", "."], cwd=tmp)
    run(["git", "commit", "-q", "-m", "init"], cwd=tmp)

    for mod in list(sys.modules):
        if mod == "minions" or mod.startswith("minions."):
            del sys.modules[mod]

    from minions.lifecycle import eacn_client, gru_inbox
    from minions.lifecycle.project import project_close, project_create, project_meta_json
    from minions.lifecycle.project_eacn import (
        project_eacn_create_task,
        project_eacn_send_message,
    )
    from minions.lifecycle.role import list_roles, reap_finished, register_expert, register_role
    from minions.lifecycle.wakeup import WakeupScheduler
    from minions.paths import MINIONS_ROOT, project_dir, project_role_log
    from minions.state.store import StateStore
    from minions.tools.mcp_server import GruInboxPollArgs, gru_inbox_poll

    assert root == MINIONS_ROOT, f"MINIONS_ROOT mismatch: {MINIONS_ROOT}"

    port: int | None = None
    try:
        print("[codex-collab] create project")
        project = project_create(
            real_name="Codex Collaboration Smoke Paper",
            venue="Imaginary Systems 2026",
            base_branch="HEAD",
            brief=(
                "Simulate a small research collaboration: Coder drafts an implementation "
                "plan, Expert critiques assumptions, Writer turns it into prose, Reviewer "
                "checks the artifact, and Ethics audits evidence claims."
            ),
        )
        port = project.port
        pdir = project_dir(port)
        step("project created", project.status == "active", f"port={port}")
        step("project CLAUDE.md exists", (pdir / "CLAUDE.md").exists())
        step("project AGENTS.md exists", (pdir / "AGENTS.md").exists())
        step(
            "meta.json has server id",
            bool(project_meta_json(port).read_text(encoding="utf-8")),
        )

        print("[codex-collab] register collaboration roles")
        role_names = ["noter", "coder", "experimenter", "writer", "reviewer", "ethics"]
        for role_name in role_names:
            register_role(port, role_name, poll_interval="1m")
        expert = register_expert(port, "Optimization", init_brief=None, poll_interval="1m")
        expert_name = str(expert["name"])
        all_roles = {r["name"] for r in list_roles(port)}
        expected_roles = {*role_names, expert_name}
        step("all roles registered", expected_roles <= all_roles, f"roles={sorted(all_roles)}")

        snap = eacn_client.probe_backend(port)
        discovered = {a.get("agent_id") for a in snap.get("agents", [])}
        step(
            "roles are EACN AgentCards",
            {"gru", "coder", "writer", "reviewer", "ethics", expert_name} <= discovered,
            f"agents={sorted(discovered)}",
        )

        print("[codex-collab] publish Gru task and dispatch Codex-host roles")
        task = project_eacn_create_task(
            port=port,
            description=(
                "Codex-host collaboration smoke: prepare a short implementation plan, "
                "turn it into a project note, review it, and audit unsupported claims."
            ),
            invited_roles=["coder", "writer", expert_name],
            expected_output={
                "type": "collaboration_smoke",
                "description": "Role status/checkpoint messages and logs.",
            },
        )
        step("Gru task created", bool(task.get("task", {}).get("task_id") or task.get("task")))

        scheduler = WakeupScheduler(store=StateStore(), cooldown_seconds=0)
        first_triggered = asyncio.run(scheduler.tick_once())
        time.sleep(0.5)
        reap_finished(store=StateStore())
        step(
            "WakeupScheduler dispatched Codex-host roles",
            first_triggered >= 3,
            f"triggered={first_triggered}",
        )

        for role_name in ("coder", "writer", expert_name):
            log = wait_for_log(project_role_log(port, role_name), "FAKE_CODEX_STDIN_END")
            step(
                f"{role_name} launched through codex exec",
                "FAKE_CODEX_ARGV: exec" in log
                and f"FAKE_CODEX_ROLE: {role_name}" in log
                and "Claude-only flag" not in log,
            )

        print("[codex-collab] simulate role-to-role collaboration messages")
        coder_to_writer = {
            "kind": "implementation_plan",
            "artifact": "workspace/codex-collab-plan.md",
            "summary": "Coder proposes a minimal implementation plan for Writer.",
        }
        project_eacn_send_message(
            port=port,
            from_role="coder",
            to_role="writer",
            content=coder_to_writer,
        )
        writer_events = eacn_client.poll_events(port, "writer", timeout_secs=1)
        step(
            "Coder -> Writer EACN message delivered",
            contains_payload(writer_events, coder_to_writer),
            f"count={writer_events.get('count')}",
        )

        writer_to_reviewer = {
            "kind": "draft_ready",
            "artifact": "workspace/codex-collab-draft.md",
            "summary": "Writer asks Reviewer for a quick formal check.",
        }
        project_eacn_send_message(
            port=port,
            from_role="writer",
            to_role="reviewer",
            content=writer_to_reviewer,
        )

        ethics_to_gru = {
            "kind": "evidence_audit",
            "summary": "Ethics notes the smoke artifact has no unsupported live claims.",
        }
        project_eacn_send_message(
            port=port,
            from_role="ethics",
            to_agent_id="gru",
            content=ethics_to_gru,
        )

        message_scheduler = WakeupScheduler(store=StateStore(), cooldown_seconds=0)
        second_triggered = asyncio.run(message_scheduler.tick_once())
        time.sleep(0.5)
        reap_finished(store=StateStore())
        reviewer_log = wait_for_log(project_role_log(port, "reviewer"), "FAKE_CODEX_STDIN_END")
        step(
            "Writer -> Reviewer triggered Codex Reviewer",
            second_triggered >= 1 and "FAKE_CODEX_ROLE: reviewer" in reviewer_log,
            f"triggered={second_triggered}",
        )

        gru_poll = gru_inbox_poll(GruInboxPollArgs(port=port))
        gru_entries = gru_inbox.read_unread(port, max_events=20)
        step(
            "Ethics -> Gru queue delivered",
            any(
                entry.get("event", {}).get("payload", {}).get("content") == ethics_to_gru
                for entry in gru_entries
            ),
            f"polled={gru_poll['polled']} unread={len(gru_entries)}",
        )

        print("[codex-collab] trigger human wakeup through Codex host")
        human = scheduler.trigger_role(port, "noter", reason="Summarize Codex collaboration smoke.")
        time.sleep(0.5)
        reap_finished(store=StateStore())
        noter_log = wait_for_log(project_role_log(port, "noter"), "FAKE_CODEX_STDIN_END")
        step(
            "manual Noter wakeup launched through Codex",
            human.get("triggered") is True
            and "FAKE_CODEX_ROLE: noter" in noter_log
            and "human_trigger" in noter_log,
            f"trigger={human}",
        )

        project_close(port)
        port = None
    finally:
        if port is not None:
            with contextlib.suppress(Exception):
                project_close(port)
        print(f"[codex-collab] cleaning up {tmp}")
        shutil.rmtree(tmp, ignore_errors=True)

    if FAILURES:
        print(f"\n[codex-collab] FAILED: {len(FAILURES)} step(s): {FAILURES}")
        return 1
    print("\n[codex-collab] ALL STEPS PASSED ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
