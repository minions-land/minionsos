"""End-to-end field test for the signboard.

Boots a real per-test project tree, walks through the full submit_ready
milestone flow (raise → evaluate → consume → reopen → re-raise), prints
timings and the on-disk JSON shape, and stress-tests concurrent writers
through the shared flock.

Run with: uv run pytest tests/unit/test_signboard_e2e.py -s
The -s flag is what makes the timing prints visible. Without it the test
still passes (correctness assertions stand on their own).
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from minions.lifecycle import project as project_mod
from minions.paths import (
    project_dir,
    project_signboard_json,
    project_state_dir,
    project_workspace_root,
)


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    author = tmp_path / "author"
    projects_root = tmp_path / "projects-root"
    author.mkdir()
    projects_root.mkdir()
    _git(["init", "-q"], author)
    _git(["config", "user.email", "t@e.com"], author)
    _git(["config", "user.name", "test"], author)
    (author / "README.md").write_text("init\n", encoding="utf-8")
    _git(["add", "."], author)
    _git(["commit", "-qm", "init"], author)

    monkeypatch.setenv("MINIONS_AUTHOR_REPO", str(author))
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(projects_root))

    port = 39977
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))

    project_dir(port).mkdir(parents=True, exist_ok=True)
    project_workspace_root(port).mkdir(parents=True, exist_ok=True)
    project_state_dir(port).mkdir(parents=True, exist_ok=True)

    project_mod._seed_per_project_repo(port)
    project_mod._create_worktree(port, "HEAD")
    project_mod._create_shared_worktree(port)

    from minions.tools import signboard as sb

    monkeypatch.setattr(sb, "_notify_gru", lambda *_a, **_kw: None)

    return {"port": port, "projects_root": projects_root, "author": author}


def test_e2e_submit_ready_full_flow(
    project: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Walk through the full submit_ready milestone end-to-end."""
    from minions.tools import signboard as sb

    port = project["port"]
    monkeypatch.setattr(
        sb,
        "_registered_expert_ids",
        lambda _p: ["expert-bio", "expert-chem", "expert-stat"],
    )

    voters = [
        ("expert-bio", "exp/exp-042/report.md#L120-160"),
        ("expert-chem", "branches/shared/notes/2026-05-19-chem-review.md"),
        ("expert-stat", "branches/shared/notes/stat-recheck.md"),
        ("ethics", "branches/shared/ethics/round-3-audit.md"),
        ("coder", "exp/exp-042/report.md (final pass, 95% CI)"),
        ("writer", "branches/writer/draft.tex@a3f7c91"),
    ]

    print(f"\n=== submit_ready field test (port={port}) ===")
    raise_times = []
    eval_times = []

    for role, evidence in voters:
        monkeypatch.setenv("MINIONS_ROLE_NAME", role)
        monkeypatch.setenv("MINIONS_AGENT_ID", role)
        t0 = time.perf_counter()
        res = sb.mos_signboard_set(milestone="submit_ready", raised=True, evidence=evidence)
        dt_raise = time.perf_counter() - t0

        t1 = time.perf_counter()
        verdict = sb.evaluate_quorum(port, "submit_ready")
        dt_eval = time.perf_counter() - t1

        raise_times.append(dt_raise * 1000)
        eval_times.append(dt_eval * 1000)
        print(
            f"  raise[{role:<14s}] {dt_raise * 1000:6.1f} ms | "
            f"evaluate {dt_eval * 1000:5.1f} ms | "
            f"met={verdict['met']} | "
            f"raised_count={len(verdict['raised'])}/"
            f"{len(verdict['fixed_required']) + verdict['experts_required_count']}"
        )
        assert res["raised_now"] is True
        assert res["agent_id"] == role

    final = sb.evaluate_quorum(port, "submit_ready")
    assert final["met"] is True, f"quorum should be met after all signs raised, got {final}"

    # Inspect the on-disk JSON.
    json_path = project_signboard_json(port)
    state = json.loads(json_path.read_text(encoding="utf-8"))
    submit_slot = state["milestones"]["submit_ready"]
    print("\n--- signboard.json submit_ready slot ---")
    print(json.dumps(submit_slot, indent=2)[:600])

    # Gru consumes after dispatching review.
    t0 = time.perf_counter()
    consume_res = sb.consume_milestone(port, "submit_ready")
    dt_consume = (time.perf_counter() - t0) * 1000
    print(f"\nconsume:    {dt_consume:5.1f} ms | round={consume_res['consumed_round']}")
    assert consume_res["changed"] is True

    # A late lower attempt is now a no-op.
    monkeypatch.setenv("MINIONS_ROLE_NAME", "expert-stat")
    monkeypatch.setenv("MINIONS_AGENT_ID", "expert-stat")
    late = sb.mos_signboard_set(milestone="submit_ready", raised=False, reason="late retraction")
    assert late.get("noop_reason") == "milestone_already_consumed"
    print(f"late lower: rejected as expected → noop_reason={late['noop_reason']!r}")

    # Reopen for a rebuttal round.
    sb.reopen_milestone(port, "submit_ready")
    after = sb.mos_signboard_read(milestone="submit_ready")
    assert after["slot"]["raised"] == {}
    assert after["slot"]["consumed_at"] is None
    assert after["slot"]["consumed_round"] == 1  # audit history preserved
    print(
        f"reopen:     raised cleared, consumed_round={after['slot']['consumed_round']} preserved\n"
    )

    # Timing summary.
    avg_raise = sum(raise_times) / len(raise_times)
    avg_eval = sum(eval_times) / len(eval_times)
    p95_raise = (
        sorted(raise_times)[int(len(raise_times) * 0.95)]
        if len(raise_times) > 1
        else raise_times[0]
    )
    print("=== timing summary ===")
    print(
        f"  raise:    avg={avg_raise:6.1f} ms  p95={p95_raise:6.1f} ms  "
        f"(file lock + json + git noop)"
    )
    print(f"  evaluate: avg={avg_eval:6.1f} ms")
    print(f"  consume:  {dt_consume:6.1f} ms")

    # Sanity bounds — these should be well under a second on a working laptop.
    assert avg_raise < 500, f"raise should be sub-500ms, got avg={avg_raise:.1f}"
    assert avg_eval < 200, f"evaluate should be sub-200ms, got avg={avg_eval:.1f}"


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


def _worker_raise(port: int, projects_root: str, author: str, role: str) -> dict:
    """Subprocess worker that raises a sign for *role* on *port*."""
    os.environ["MINIONS_AUTHOR_REPO"] = author
    os.environ["MINIONS_PROJECTS_ROOT"] = projects_root
    os.environ["MINIONS_PROJECT_PORT"] = str(port)
    os.environ["MINIONS_ROLE_NAME"] = role
    os.environ["MINIONS_AGENT_ID"] = role
    # Imports happen inside the worker so each subprocess gets a fresh module
    # state and the env vars above are picked up.
    from minions.tools import signboard as sb

    sb._notify_gru = lambda *_a, **_kw: None  # type: ignore[assignment]
    res = sb.mos_signboard_set(
        milestone="experiments_ready",
        raised=True,
        evidence=f"exp/exp-042/{role}.md",
    )
    return {"role": role, "raised_now": res["raised_now"]}


def test_concurrent_writers_under_flock(project: dict[str, Any]) -> None:
    """Five subprocesses all hammer mos_signboard_set on the same project.

    The shared flock should serialize them and every sign should land in
    the final JSON — no torn writes, no lost updates.
    """
    port = project["port"]
    voters = ["expert-a", "expert-b", "expert-c", "ethics", "coder"]

    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=len(voters)) as pool:
        t0 = time.perf_counter()
        results = pool.starmap(
            _worker_raise,
            [
                (port, str(project["projects_root"]), str(project["author"]), role)
                for role in voters
            ],
        )
        dt = (time.perf_counter() - t0) * 1000

    print("\n=== concurrent writers ===")
    print(f"  {len(voters)} workers, total wall-clock {dt:6.1f} ms")
    for r in results:
        assert r["raised_now"] is True, f"{r['role']} did not land"

    # Read state directly from disk — nothing should be lost.
    state = json.loads(project_signboard_json(port).read_text(encoding="utf-8"))
    raised = state["milestones"]["experiments_ready"]["raised"]
    print(f"  signboard.raised keys: {sorted(raised.keys())}")
    for role in voters:
        assert role in raised, (
            f"{role} sign was lost despite flock. Got keys: {sorted(raised.keys())}"
        )
    # Each entry must carry that role's evidence — no cross-contamination.
    for role in voters:
        assert raised[role]["evidence"] == f"exp/exp-042/{role}.md"


def test_idempotent_re_raise(project: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """Same agent raising twice with new evidence updates rather than
    duplicating. Final state should reflect the latest evidence."""
    from minions.tools import signboard as sb

    monkeypatch.setenv("MINIONS_ROLE_NAME", "ethics")
    monkeypatch.setenv("MINIONS_AGENT_ID", "ethics")
    sb.mos_signboard_set(milestone="experiments_ready", raised=True, evidence="ethics/v1.md")
    sb.mos_signboard_set(milestone="experiments_ready", raised=True, evidence="ethics/v2.md")
    state = sb.mos_signboard_read(milestone="experiments_ready")
    assert state["slot"]["raised"]["ethics"]["evidence"] == "ethics/v2.md"
    # Only one entry per agent_id, no duplication.
    assert len(state["slot"]["raised"]) == 1
