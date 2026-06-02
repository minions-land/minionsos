"""End-to-end integration test for the compact pipeline (issue #38).

Phases tested:
  1. mos_compact_context persists pending_plans + writes journal + tmux send-keys
  2. PreCompact hook emits pointer-shaped instructions citing 3 memory layers
  3. PostCompact hook extracts node refs and writes audit entry
  4. Post-compact role's mos_draft_summary surfaces pending plans
  5. Pattern A: high pressure + queue non-empty → annotate first event
  6. Pattern B: high pressure + queue empty → preempt compact + synthetic event
  7. End-to-end: full cognitive-checkpoint loop with all phases stitched
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PRE_HOOK = REPO_ROOT / "minions" / "hooks" / "pre_compact_science.py"
POST_HOOK = REPO_ROOT / "minions" / "hooks" / "post_compact_draft.py"


def _write_session_jsonl(path: Path, cr_values: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for i, cr in enumerate(cr_values):
        lines.append(
            json.dumps(
                {
                    "type": "assistant",
                    "timestamp": f"2026-05-27T00:{i:02d}:00Z",
                    "sessionId": "fake-session",
                    "cwd": "/fake",
                    "message": {
                        "usage": {
                            "cache_read_input_tokens": cr,
                            "cache_creation_input_tokens": 100,
                            "input_tokens": 1000,
                            "output_tokens": 100,
                        }
                    },
                }
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _setup_project(tmp_path: Path, port: int = 88888) -> dict:
    projects_root = tmp_path / "projects"
    project_dir = projects_root / f"project_{port}"
    workspace = project_dir / "branches" / "expert-foo"
    workspace.mkdir(parents=True)
    # v23 main=Book: the shared cross-role surface IS the main-branch worktree
    # (project_shared_subdir → branches/main/). The fixture must mirror that or
    # journal/draft writes land where the test does not look.
    shared = project_dir / "branches" / "main"
    (shared / "draft").mkdir(parents=True)
    (shared / "book").mkdir(parents=True)
    (shared / "exp").mkdir(parents=True)
    draft_path = shared / "draft" / "draft.json"
    draft_path.write_text(
        json.dumps(
            {
                "nodes": [
                    {"id": "H-001", "type": "hypothesis", "text": "MoE routing test"},
                    {"id": "E-001", "type": "experiment", "text": "Triton kernel benchmark"},
                ],
                "edges": [],
            }
        )
    )
    return {
        "tmp_path": tmp_path,
        "projects_root": projects_root,
        "project_dir": project_dir,
        "workspace": workspace,
        "shared": shared,
        "draft_path": draft_path,
        "port": port,
        "role": "expert-foo",
    }


def _run_hook(hook: Path, stdin: str, env: dict) -> subprocess.CompletedProcess:
    proc_env = os.environ.copy()
    proc_env.pop("MINIONS_PROJECTS_ROOT", None)
    proc_env.update(env)
    return subprocess.run(
        [sys.executable, str(hook)],
        input=stdin,
        capture_output=True,
        text=True,
        env=proc_env,
        check=False,
        timeout=15,
    )


# ─── Phase 1: mos_compact_context persists Draft + journal + tmux ─────────


def test_phase1_compact_context_persists_pending_plans_and_schedules(
    tmp_path: Path, monkeypatch
) -> None:
    proj = _setup_project(tmp_path)
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(proj["port"]))
    monkeypatch.setenv("MINIONS_ROLE_NAME", proj["role"])
    monkeypatch.setenv("MINIONS_AGENT_ID", proj["role"])
    monkeypatch.setenv("MINIONS_WORKSPACE", str(proj["workspace"]))
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(proj["projects_root"]))

    schedule_calls: list = []

    def _fake_schedule(session, reason):
        schedule_calls.append((session, reason))
        return True

    from minions.tools import compact as _compact_mod

    monkeypatch.setattr(_compact_mod, "_schedule_compact", _fake_schedule)

    from minions.tools.compact import mos_compact_context

    pending = [
        {
            "type": "question",
            "text": (
                "Writer requests Coder refactor data-loader for arbitrary "
                "tokenizers. Originating event from writer@2026-05-27T00:30Z."
            ),
        },
        {"type": "experiment", "text": "Sweep learning rate {1e-4, 5e-4, 1e-3} for 12B variant."},
    ]
    result = mos_compact_context(reason="batch had unrelated events", pending_plans=pending)

    journal = proj["shared"] / "draft" / "journal.jsonl"
    assert journal.exists()
    entries = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
    compact_entries = [e for e in entries if e.get("op") == "compact"]
    assert len(compact_entries) == 1
    assert compact_entries[0]["role"] == proj["role"]
    assert compact_entries[0]["reason"] == "batch had unrelated events"

    draft = json.loads(proj["draft_path"].read_text())
    pending_nodes = [n for n in draft["nodes"] if n.get("metadata", {}).get("pending_plan")]
    assert len(pending_nodes) == 2, f"Got {pending_nodes}"
    pending_texts = [n["text"] for n in pending_nodes]
    assert any("data-loader" in t for t in pending_texts)
    assert any("learning rate" in t for t in pending_texts)
    assert len(result["draft_nodes_persisted"]) == 2

    assert len(schedule_calls) == 1
    assert schedule_calls[0][0] == f"mos-{proj['port']}-{proj['role']}"
    assert result["status"] == "compact_scheduled"


# ─── Phase 2: PreCompact emits pointer-shaped, layer-aware instructions ────


def test_phase2_precompact_emits_pointer_shaped_instructions(tmp_path: Path) -> None:
    proj = _setup_project(tmp_path)
    env = {
        "MINIONS_PROJECT_PORT": str(proj["port"]),
        "MINIONS_ROLE_NAME": proj["role"],
        "MINIONS_PROJECTS_ROOT": str(proj["projects_root"]),
    }
    payload = {"trigger": "manual", "custom_instructions": "User said: be terse"}
    result = _run_hook(PRE_HOOK, json.dumps(payload), env=env)
    assert result.returncode == 0, f"stderr: {result.stderr}"
    out = result.stdout
    assert "User said: be terse" in out
    assert "L1 — Draft" in out
    assert "L2 — Book" in out
    assert "L3 — Shelf" in out
    assert "Cite IDs and paths" in out or "cite IDs and paths" in out
    assert "## Resume_protocol" in out
    assert "mos_await_events" in out
    assert "H-###" in out or "H-001" in out


# ─── Phase 3: PostCompact extracts and audits ──────────────────────────────


def test_phase3_postcompact_extracts_and_audits_summary(tmp_path: Path) -> None:
    proj = _setup_project(tmp_path)
    transcript = tmp_path / "session.jsonl"
    summary_md = """## Working_on
- E-001 — Triton kernel benchmark in progress.

## Next_action
- mos_draft_summary() then mos_await_events()

## New_or_changed_nodes
- E-002 — new follow-up experiment (tentative)
- DEAD-001 — abandoned approach (abandoned)

## Pending_plans
- Q-001 — Writer's data-loader refactor (already persisted with metadata.pending_plan=true)

## Open_questions
- Q-002 — does H-001 hold under FP8?

## Notes
- Routing through n42_kernels community on Shelf.

## Resume_protocol
mos_draft_summary() → mos_await_events()
"""
    lines = [
        json.dumps(
            {"type": "assistant", "message": {"usage": {"cache_read_input_tokens": 150_000}}}
        ),
        json.dumps(
            {
                "type": "system",
                "subtype": "compact_boundary",
                "compactMetadata": {"trigger": "manual", "preTokens": 165_000},
            }
        ),
        json.dumps(
            {
                "type": "user",
                "isCompactSummary": True,
                "message": {"role": "user", "content": summary_md},
            }
        ),
    ]
    transcript.write_text("\n".join(lines) + "\n")

    env = {
        "MINIONS_PROJECT_PORT": str(proj["port"]),
        "MINIONS_ROLE_NAME": proj["role"],
        "MINIONS_PROJECTS_ROOT": str(proj["projects_root"]),
    }
    payload = {"transcript_path": str(transcript), "trigger": "manual"}
    result = _run_hook(POST_HOOK, json.dumps(payload), env=env)
    assert result.returncode == 0, f"stderr: {result.stderr}"

    journal = proj["shared"] / "draft" / "journal.jsonl"
    entries = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
    extracts = [e for e in entries if e.get("op") == "post_compact_extract"]
    assert len(extracts) == 1
    ex = extracts[0]["extract"]
    assert "E-001" in ex["working_on"]
    assert "E-002" in ex["new_or_changed_node_ids"]
    assert "DEAD-001" in ex["new_or_changed_node_ids"]
    assert "Q-001" in ex["pending_plan_node_ids"]
    assert "E-001" in ex["known_node_refs"]
    assert "E-002" in ex["unknown_node_refs"]
    assert "Q-001" in ex["unknown_node_refs"]


# ─── Phase 4: post-compact role re-orients via mos_draft_summary ──────────


def test_phase4_post_compact_role_sees_pending_plans(tmp_path: Path, monkeypatch) -> None:
    """After cognitive-checkpoint persists pending_plans + compact fires, the
    post-compact role's first call (mos_draft_summary) MUST surface those
    pending plans. This is the bridge that lets 'compact后继续做无关任务' work.
    """
    proj = _setup_project(tmp_path)
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(proj["port"]))
    monkeypatch.setenv("MINIONS_ROLE_NAME", proj["role"])
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(proj["projects_root"]))
    from minions.tools import compact as _compact_mod

    monkeypatch.setattr(_compact_mod, "_schedule_compact", lambda session, reason: True)

    from minions.tools.compact import mos_compact_context

    mos_compact_context(
        reason="setup",
        pending_plans=[
            {"type": "question", "text": "Writer's data-loader refactor request — pending."},
        ],
    )

    from minions.tools.draft import mos_draft_summary

    summary = mos_draft_summary()
    pending = summary.get("pending_plans") or []
    assert pending, f"summary keys: {list(summary.keys())}"
    # The pending node text mentions 'data-loader'
    pending_texts = [str(p) for p in pending]
    assert any("data-loader" in t for t in pending_texts)


# ─── Phase 5: Pattern A annotates first event when queue non-empty ────────


def test_phase5_pattern_a_annotates_event_at_high_pressure(tmp_path: Path, monkeypatch) -> None:
    proj = _setup_project(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(proj["port"]))
    monkeypatch.setenv("MINIONS_ROLE_NAME", proj["role"])
    monkeypatch.setenv("MINIONS_AGENT_ID", proj["role"])
    monkeypatch.setenv("MINIONS_WORKSPACE", str(proj["workspace"]))
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(proj["projects_root"]))

    from minions.tools import context_pressure as cp

    slug = cp._slug_for_workspace(proj["workspace"])
    sd = home / ".claude" / "projects" / slug
    sd.mkdir(parents=True)
    _write_session_jsonl(sd / "s.jsonl", [120_000] * 10)
    cp.reset_memo()

    fake_evt = {
        "event_id": "e1",
        "type": "direct_message",
        "payload": {"from": "writer", "content": "Need refactor"},
    }
    from minions.tools import await_events as ae

    monkeypatch.setattr(ae, "_poll_once", lambda port, agent_id: [fake_evt])
    monkeypatch.setattr(ae, "_load_keepalive_seconds", lambda: 0)
    monkeypatch.setattr(ae, "_touch_heartbeat", lambda ws, aid: None)
    monkeypatch.setattr(ae, "_schedule_preemptive_compact", lambda port, agent_id: True)

    import sys as _sys
    import types as _types

    fake_log = _types.ModuleType("minions.tools.events_log")
    fake_log.append_events = lambda *a, **k: None
    monkeypatch.setitem(_sys.modules, "minions.tools.events_log", fake_log)
    fake_audit = _types.ModuleType("minions.tools.draft_audit")

    class _Snap:
        reminder_due = False
        prev_delivery_was_real = False

    fake_audit.take_snapshot_and_reset = lambda *a, **k: _Snap()
    monkeypatch.setitem(_sys.modules, "minions.tools.draft_audit", fake_audit)

    result = ae.await_events()
    assert result["count"] == 1
    evt = result["events"][0]
    assert "context_pressure" in evt
    assert evt["context_pressure"]["level"] == "high"
    assert "mos_compact_context" in evt["suggested_action"]


# ─── Phase 6: Pattern B preempts compact when queue idle ──────────────────


def test_phase6_pattern_b_preempts_compact_when_idle(tmp_path: Path, monkeypatch) -> None:
    proj = _setup_project(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(proj["port"]))
    monkeypatch.setenv("MINIONS_ROLE_NAME", proj["role"])
    monkeypatch.setenv("MINIONS_AGENT_ID", proj["role"])
    monkeypatch.setenv("MINIONS_WORKSPACE", str(proj["workspace"]))
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(proj["projects_root"]))

    from minions.tools import context_pressure as cp

    slug = cp._slug_for_workspace(proj["workspace"])
    sd = home / ".claude" / "projects" / slug
    sd.mkdir(parents=True)
    _write_session_jsonl(sd / "s.jsonl", [120_000] * 10)
    cp.reset_memo()

    from minions.tools import await_events as ae

    schedule_calls = []

    def _fake_schedule(port, agent_id):
        schedule_calls.append((port, agent_id))
        from minions.paths import project_shared_subdir

        d = project_shared_subdir(port, "draft")
        d.mkdir(parents=True, exist_ok=True)
        (d / "journal.jsonl").open("a").write(
            json.dumps(
                {
                    "op": "compact",
                    "role": "expert-foo",
                    "reason": "context_pressure_preemptive",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            + "\n"
        )
        return True

    monkeypatch.setattr(ae, "_poll_once", lambda port, agent_id: [])
    monkeypatch.setattr(ae, "_schedule_preemptive_compact", _fake_schedule)
    monkeypatch.setattr(ae, "_load_keepalive_seconds", lambda: 0)
    monkeypatch.setattr(ae, "_touch_heartbeat", lambda ws, aid: None)

    result = ae.await_events()
    assert result["count"] == 1
    evt = result["events"][0]
    assert evt["event"]["type"] == "context_pressure_compact"
    assert "preemptively" in evt["suggested_action"].lower()
    assert len(schedule_calls) == 1
    assert schedule_calls[0] == (proj["port"], proj["role"])

    cp.reset_memo()
    next_pressure = cp.probe(workspace=proj["workspace"])
    assert next_pressure.on_cooldown is True
    assert next_pressure.level == "medium"


# ─── Phase 7: full cognitive-checkpoint loop ─────────────────────────────


def test_phase7_end_to_end_pipeline(tmp_path: Path, monkeypatch) -> None:
    """Walk the entire pipeline from EACN event arrival to post-compact
    pending_plan visibility:

      (a) role calls mos_compact_context with pending_plans (Phase 1 logic)
      (b) PreCompact emits pointer-shaped instructions (Phase 2)
      (c) PostCompact extracts and audits (Phase 3)
      (d) post-compact role's mos_draft_summary surfaces pending plans (Phase 4)

    The closure: the pending_plan node id created by (a) must round-trip
    through the compact summary, end up in (c)'s post_compact_extract, AND
    still be visible to the post-compact role in (d).
    """
    proj = _setup_project(tmp_path)
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(proj["port"]))
    monkeypatch.setenv("MINIONS_ROLE_NAME", proj["role"])
    monkeypatch.setenv("MINIONS_AGENT_ID", proj["role"])
    monkeypatch.setenv("MINIONS_WORKSPACE", str(proj["workspace"]))
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(proj["projects_root"]))

    # Patch _schedule_compact (the tmux helper inside compact.py) so we
    # don't touch real terminals. _run_hook uses a separate subprocess.run
    # for the hook subprocesses, which we must NOT patch.
    from minions.tools import compact as _compact_mod

    monkeypatch.setattr(_compact_mod, "_schedule_compact", lambda session, reason: True)

    # (a) cognitive-checkpoint: persist pending_plans + schedule compact
    from minions.tools.compact import mos_compact_context

    pending = [
        {
            "type": "question",
            "text": (
                "Writer asked Coder to refactor data-loader (event writer@2026-05-27T00:30Z)."
            ),
        },
    ]
    result = mos_compact_context(reason="batch had unrelated events", pending_plans=pending)
    assert result["status"] == "compact_scheduled"
    assert len(result["draft_nodes_persisted"]) == 1
    pending_id = result["draft_nodes_persisted"][0]

    # (b) PreCompact runs
    pre_env = {
        "MINIONS_PROJECT_PORT": str(proj["port"]),
        "MINIONS_ROLE_NAME": proj["role"],
        "MINIONS_PROJECTS_ROOT": str(proj["projects_root"]),
    }
    pre_result = _run_hook(PRE_HOOK, json.dumps({"trigger": "manual"}), env=pre_env)
    assert pre_result.returncode == 0
    assert "mos_await_events" in pre_result.stdout

    # (c) Simulate compact_boundary + summary in transcript, run PostCompact
    transcript = tmp_path / "session.jsonl"
    summary_md = f"""## Working_on
- E-001 in progress.

## Next_action
- mos_draft_summary() then mos_await_events()

## Pending_plans
- {pending_id} — Writer data-loader refactor (already persisted)

## Resume_protocol
mos_draft_summary() → mos_await_events()
"""
    transcript.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "system",
                        "subtype": "compact_boundary",
                        "compactMetadata": {"trigger": "manual", "preTokens": 165_000},
                    }
                ),
                json.dumps(
                    {
                        "type": "user",
                        "isCompactSummary": True,
                        "message": {"role": "user", "content": summary_md},
                    }
                ),
            ]
        )
        + "\n"
    )
    post_result = _run_hook(
        POST_HOOK,
        json.dumps({"transcript_path": str(transcript), "trigger": "manual"}),
        env=pre_env,
    )
    assert post_result.returncode == 0

    # Journal must have BOTH op:compact and op:post_compact_extract
    journal = proj["shared"] / "draft" / "journal.jsonl"
    entries = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
    ops = [e["op"] for e in entries]
    assert "compact" in ops
    assert "post_compact_extract" in ops

    # The pending_id created in (a) must appear in (c)'s extract.pending_plan_node_ids,
    # AND it must now be classified as "known" because (a) already wrote it to draft.json
    extract = next(e["extract"] for e in entries if e["op"] == "post_compact_extract")
    assert pending_id in extract["pending_plan_node_ids"]
    assert pending_id in extract["known_node_refs"]
    assert pending_id not in extract["unknown_node_refs"]

    # (d) Post-compact role calls mos_draft_summary; pending plan surfaces
    from minions.tools.draft import mos_draft_summary

    summary = mos_draft_summary()
    pending_in_summary = summary.get("pending_plans") or []
    assert pending_in_summary, (
        f"Post-compact role would NOT see deferred work! summary keys: {list(summary.keys())}"
    )
    assert any("data-loader" in str(p) for p in pending_in_summary)
