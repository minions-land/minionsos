#!/usr/bin/env python3
"""Context-tax slim validation harness.

Spawns minimal claude --print invocations with an Expert Role's actual
configuration (allowed_tools, MCP config, system prompt, env), measures
input_tokens, and compares ENABLE_TOOL_SEARCH=false vs auto:30.

This is the minimum-viable validation: a single cold-start measurement
per config. It directly measures the dominant cost — system prompt size.
A full multi-turn cache-hit-rate measurement requires a live Role spawn.

Usage:
    uv run python tests/manual/measure_context_slim.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from minions.config import GruConfig, whitelist_csv  # noqa: E402
from minions.lifecycle.agent_host import build_role_invocation  # noqa: E402
from minions.lifecycle.role_launcher import _role_env  # noqa: E402
from minions.paths import common_role_system_md  # noqa: E402
from minions.state.store import RoleEntry  # noqa: E402

ROLE_NAME = "expert"
PROJECT_PORT = 99999  # ephemeral; no real backend


def fresh_prompt() -> str:
    import random

    return f"Reply 'ok{random.randint(100000, 999999)}'."


def build_invocation(tool_search_value: str) -> tuple[list[str], dict[str, str]]:
    """Return the launch argv/env while overriding ENABLE_TOOL_SEARCH."""
    cfg = GruConfig()
    allowed = whitelist_csv(ROLE_NAME, "main")

    # Build a workspace path under /tmp so the agent has a cwd
    workspace = Path("/tmp/measure-expert")
    workspace.mkdir(exist_ok=True)

    invocation = build_role_invocation(
        cfg=cfg,
        role_name=ROLE_NAME,
        project_port=PROJECT_PORT,
        project_agent_id=ROLE_NAME,
        system_path=common_role_system_md(),
        allowed_tools=allowed,
        workspace=workspace,
        session_name="measure",
    )

    # Reuse the launcher's env builder for fidelity
    env = os.environ.copy()
    fake_entry = RoleEntry(
        name=ROLE_NAME,
        state="active",
        eacn_agent_id=ROLE_NAME,
        workspace_branch="main",
        github_push_target=None,
    )
    overrides = _role_env(
        role_name=ROLE_NAME,
        project_port=PROJECT_PORT,
        role_entry=fake_entry,
        workspace=workspace,
    )
    env.update(overrides)
    env["ENABLE_TOOL_SEARCH"] = tool_search_value
    return invocation.command, env


def measure(label: str, tool_search_value: str) -> dict:
    print(f"\n=== Measuring: {label} (ENABLE_TOOL_SEARCH={tool_search_value}) ===", flush=True)
    cmd, env = build_invocation(tool_search_value)
    cmd = [*cmd, "--print", "--output-format", "json", fresh_prompt()]
    print(f"argv head: {' '.join(cmd[:3])} ... ({len(cmd)} args total)", flush=True)
    try:
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return {"label": label, "error": "timeout 300s"}
    if result.returncode != 0:
        print(
            f"FAILED rc={result.returncode}\n"
            f"STDOUT: {result.stdout[:500]}\n"
            f"STDERR: {result.stderr[:500]}"
        )
        return {"label": label, "error": result.stderr[:500] or result.stdout[:500]}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"label": label, "error": f"non-JSON: {result.stdout[:500]}"}
    usage = payload.get("usage", {})
    return {
        "label": label,
        "tool_search": tool_search_value,
        "input_tokens": usage.get("input_tokens", 0),
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
        "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "total_cost_usd": payload.get("total_cost_usd"),
        "duration_ms": payload.get("duration_ms"),
    }


def main() -> int:
    results = []
    for label, val in [("BASELINE_eager_load", "false"), ("AFTER_auto_30", "auto:30")]:
        r = measure(label, val)
        results.append(r)
        print(json.dumps(r, indent=2))

    print("\n=== SUMMARY ===")
    if all("error" not in r for r in results):
        b = results[0]
        a = results[1]
        b_total = (
            b["input_tokens"] + b["cache_creation_input_tokens"] + b["cache_read_input_tokens"]
        )
        a_total = (
            a["input_tokens"] + a["cache_creation_input_tokens"] + a["cache_read_input_tokens"]
        )
        delta = a_total - b_total
        pct = (delta / b_total * 100) if b_total else 0
        print(f"BASELINE total input tokens (false):   {b_total:>8}")
        print(f"AFTER total input tokens (auto:30):    {a_total:>8}")
        print(f"DELTA: {delta:+d} tokens ({pct:+.1f}%)")
        print(f"Gate (input <75k): {'PASS' if a_total < 75000 else 'FAIL'} (saw {a_total})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
