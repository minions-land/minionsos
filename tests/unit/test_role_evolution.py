"""Tests for minions.lifecycle.role_evolution.

Covers the pure-logic surface (clustering, scoring, evidence-gated
decisions) plus the apply paths via monkeypatched spawn/dismiss.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from minions.lifecycle import role_evolution as RE
from minions.state.store import ProjectEntry, RoleEntry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ev(role: str, source: str, text: str, hours_ago: float = 1.0) -> RE.FailureEvent:
    when = datetime.now(UTC) - timedelta(hours=hours_ago)
    return RE.FailureEvent(
        role_name=role,
        when=when,
        source=source,  # type: ignore[arg-type]
        text=text,
        artifact_path=f"branches/shared/{source}/auto.md",
    )


def _stats(
    name: str, n_tasks: int, age_hours: float = 24.0, artifacts: list[str] | None = None
) -> RE.RoleStats:
    return RE.RoleStats(
        role_name=name,
        age_hours=age_hours,
        age_since_last_evolution_hours=None,
        n_tasks_recent=n_tasks,
        n_messages_recent=n_tasks,
        artifacts_recent=artifacts or [],
    )


# ---------------------------------------------------------------------------
# Tunables loading
# ---------------------------------------------------------------------------


def test_load_tunables_uses_defaults_when_no_config():
    t = RE.load_tunables(None)
    assert t.split_min_failures == 5
    assert t.merge_convergence_threshold == 0.75


def test_load_tunables_overrides_from_gru_yaml_section():
    cfg = {
        "role_evolution": {
            "split_min_failures": 3,
            "merge_convergence_threshold": 0.9,
        }
    }
    t = RE.load_tunables(cfg)
    assert t.split_min_failures == 3
    assert t.merge_convergence_threshold == 0.9


# ---------------------------------------------------------------------------
# Failure clustering
# ---------------------------------------------------------------------------


def test_cluster_failures_buckets_by_keyword():
    events = [
        _ev("coder", "experiment", "convergence diverges in this run"),
        _ev("coder", "experiment", "loss spike at step 100"),
        _ev("coder", "ethics", "p-value reporting was misleading"),
        _ev("coder", "ethics", "hypothesis stated post-hoc"),
        _ev("coder", "experiment", "no relevant keywords here"),
    ]
    clusters = {c.label: c.n for c in RE.cluster_failures(events)}
    assert clusters["optimization"] == 2
    assert clusters["statistics"] == 2
    assert clusters["misc"] == 1


def test_cluster_failures_misc_is_not_load_bearing():
    """misc bucket can be huge but does not satisfy the SPLIT trigger."""
    events = [_ev("coder", "experiment", "totally unrelated noise") for _ in range(20)]
    clusters = RE.cluster_failures(events)
    misc = next(c for c in clusters if c.label == "misc")
    assert misc.n == 20
    # but evaluate_split should still say KEEP
    role = RoleEntry(name="coder", state="active")
    decision = RE.evaluate_split(role, events)
    assert decision.decision == "KEEP"


# ---------------------------------------------------------------------------
# Convergence
# ---------------------------------------------------------------------------


def test_convergence_score_zero_when_no_artifacts():
    assert RE.convergence_score(_stats("a", 0), _stats("b", 0)) == 0.0


def test_convergence_score_high_when_overlap():
    a = _stats(
        "alg",
        3,
        artifacts=["/p/branches/shared/notes/x.md", "/p/branches/shared/notes/y.md"],
    )
    b = _stats(
        "geo",
        3,
        artifacts=["/p/branches/shared/notes/x.md", "/p/branches/shared/notes/y.md"],
    )
    assert RE.convergence_score(a, b) > 0.95


def test_convergence_score_low_when_disjoint():
    a = _stats("alg", 3, artifacts=["/p/branches/shared/exp/r1.md"])
    b = _stats("geo", 3, artifacts=["/p/branches/shared/notes/n1.md"])
    assert RE.convergence_score(a, b) < 0.5


# ---------------------------------------------------------------------------
# evaluate_split
# ---------------------------------------------------------------------------


def test_split_keeps_when_too_few_failures():
    role = RoleEntry(name="coder", state="active")
    events = [
        _ev("coder", "experiment", "convergence drift"),
        _ev("coder", "experiment", "p-value off"),
    ]
    d = RE.evaluate_split(role, events)
    assert d.decision == "KEEP"
    assert "Only" in d.reason


def test_split_keeps_when_only_one_subdomain():
    role = RoleEntry(name="coder", state="active")
    events = [_ev("coder", "experiment", "loss diverged convergence") for _ in range(8)]
    d = RE.evaluate_split(role, events)
    assert d.decision == "KEEP"
    # All in optimization sub-domain → can't split
    assert "sub-domain" in d.reason


def test_split_fires_when_evidence_partitioned():
    role = RoleEntry(name="coder", state="active")
    events = [_ev("coder", "experiment", "convergence drift") for _ in range(3)] + [
        _ev("coder", "ethics", "p-value misreport") for _ in range(3)
    ]
    d = RE.evaluate_split(role, events)
    assert d.decision == "SPLIT"
    names = {s["name"] for s in d.proposed_specialists}
    assert names == {"coder-optimization", "coder-statistics"}


def test_split_only_counts_failures_for_the_target_role():
    role = RoleEntry(name="coder", state="active")
    events = [_ev("coder", "experiment", "convergence x") for _ in range(3)] + [
        _ev("writer", "ethics", "p-value y") for _ in range(3)
    ]
    d = RE.evaluate_split(role, events)
    # Only 3 attributable to coder, all in optimization → KEEP
    assert d.decision == "KEEP"


# ---------------------------------------------------------------------------
# evaluate_merge
# ---------------------------------------------------------------------------


def test_dismiss_fires_for_idle_old_role():
    """A Role that has aged past min and has no recent tasks should be
    DISMISSED, not merged. Merging a starved Role into another's scope
    is the wrong primitive — retire it instead."""
    stats = {
        "expert-old": _stats("expert-old", n_tasks=0, age_hours=24),
        "expert-busy": _stats("expert-busy", n_tasks=10, age_hours=24),
    }
    decisions = RE.evaluate_dismiss(stats)
    assert len(decisions) == 1
    assert decisions[0].decision == "DISMISS"
    assert decisions[0].role == "expert-old"
    assert decisions[0].n_tasks_recent == 0


def test_dismiss_skipped_for_young_role():
    """Even with zero tasks, a Role younger than the age threshold is
    given the benefit of the doubt — it might just have spawned."""
    stats = {
        "expert-fresh": _stats("expert-fresh", n_tasks=0, age_hours=1.0),
    }
    decisions = RE.evaluate_dismiss(stats)
    assert decisions == []


def test_evaluate_merge_does_not_emit_starvation_kind():
    """Convergence is now the only MERGE trigger; starvation goes to dismiss."""
    project = ProjectEntry(
        port=39999,
        real_name="t",
        status="active",
        created="2026-01-01T00:00:00Z",
        current_branch="x",
        active_roles=[],
    )
    stats = {
        "expert-old": _stats("expert-old", n_tasks=0, age_hours=24),
        "expert-busy": _stats("expert-busy", n_tasks=10, age_hours=24),
    }
    decisions = RE.evaluate_merge(project, stats)
    # No convergence (different artifact sets), and starvation is not a merge case.
    assert all(d.kind != "starvation" for d in decisions)


def test_merge_convergence_fires_on_independent_roles():
    """Convergence merge does NOT require split lineage."""
    project = ProjectEntry(
        port=39999,
        real_name="t",
        status="active",
        created="2026-01-01T00:00:00Z",
        current_branch="x",
        active_roles=[],
    )
    shared_paths = [
        "/p/branches/shared/notes/topic-a.md",
        "/p/branches/shared/notes/topic-b.md",
        "/p/branches/shared/notes/topic-c.md",
    ]
    stats = {
        "expert-cs-theory": _stats("cs-theory", n_tasks=5, age_hours=24, artifacts=shared_paths),
        "expert-algorithms": _stats("algorithms", n_tasks=5, age_hours=24, artifacts=shared_paths),
    }
    decisions = RE.evaluate_merge(project, stats)
    conv = [d for d in decisions if d.kind == "convergence"]
    assert len(conv) == 1
    assert sorted(conv[0].roles) == ["expert-algorithms", "expert-cs-theory"]
    assert conv[0].convergence_score is not None
    assert conv[0].convergence_score >= 0.75


# ---------------------------------------------------------------------------
# Apply: dry_run path (no spawn / dismiss)
# ---------------------------------------------------------------------------


def test_apply_split_requires_evidence_refs(tmp_path, monkeypatch):
    monkeypatch.setattr(RE, "_shared_dir", lambda port: tmp_path)
    with pytest.raises(ValueError):
        RE.apply_split(
            project_port=39999,
            source_role="coder",
            into_specs=[
                {"name": "coder-a", "charter": "x", "pitfalls": "y"},
                {"name": "coder-b", "charter": "x", "pitfalls": "y"},
            ],
            evidence_refs=[],
            reason="no evidence",
            dry_run=True,
        )


def test_apply_split_requires_at_least_two_specs(tmp_path, monkeypatch):
    monkeypatch.setattr(RE, "_shared_dir", lambda port: tmp_path)
    with pytest.raises(ValueError):
        RE.apply_split(
            project_port=39999,
            source_role="coder",
            into_specs=[{"name": "x", "charter": "y", "pitfalls": "z"}],
            evidence_refs=["branches/shared/ethics/auto.md"],
            reason="t",
            dry_run=True,
        )


def test_apply_split_dry_run_writes_audit_and_does_not_spawn(tmp_path, monkeypatch):
    monkeypatch.setattr(RE, "_shared_dir", lambda port: tmp_path)
    res = RE.apply_split(
        project_port=39999,
        source_role="coder",
        into_specs=[
            {"name": "coder-a", "charter": "alpha", "pitfalls": "p"},
            {"name": "coder-b", "charter": "beta", "pitfalls": "p"},
        ],
        evidence_refs=["branches/shared/ethics/r1.md"],
        reason="test",
        dry_run=True,
    )
    assert res.kind == "split"
    assert res.roles_in == ["coder"]
    assert sorted(res.roles_out) == ["coder-a", "coder-b"]
    assert any("dry_run" in n for n in res.notes)
    log = tmp_path / "governance" / "role_evolution.jsonl"
    assert log.exists()
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["kind"] == "split"
    assert rec["evidence_refs"] == ["branches/shared/ethics/r1.md"]


def test_apply_merge_dry_run_writes_audit(tmp_path, monkeypatch):
    monkeypatch.setattr(RE, "_shared_dir", lambda port: tmp_path)
    res = RE.apply_merge(
        project_port=39999,
        source_roles=["expert-a", "expert-b"],
        into_spec={"name": "expert-merged", "charter": "x", "pitfalls": "y"},
        evidence_refs=["auto:convergence"],
        reason="convergence detected",
        dry_run=True,
    )
    assert res.kind == "merge"
    assert sorted(res.roles_in) == ["expert-a", "expert-b"]
    assert res.roles_out == ["expert-merged"]
    log = tmp_path / "governance" / "role_evolution.jsonl"
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["kind"] == "merge"


def test_apply_dismiss_requires_evidence_refs(tmp_path, monkeypatch):
    monkeypatch.setattr(RE, "_shared_dir", lambda port: tmp_path)
    with pytest.raises(ValueError):
        RE.apply_dismiss(
            project_port=39999,
            role_name="expert-idle",
            evidence_refs=[],
            reason="t",
            dry_run=True,
        )


def test_apply_dismiss_dry_run_writes_audit(tmp_path, monkeypatch):
    monkeypatch.setattr(RE, "_shared_dir", lambda port: tmp_path)
    res = RE.apply_dismiss(
        project_port=39999,
        role_name="expert-idle",
        evidence_refs=["auto:starvation:expert-idle"],
        reason="no work in 24h",
        dry_run=True,
    )
    assert res.kind == "dismiss"
    assert res.roles_in == ["expert-idle"]
    assert res.roles_out == []
    log = tmp_path / "governance" / "role_evolution.jsonl"
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["kind"] == "dismiss"
    assert rec["roles_out"] == []


def test_apply_dismiss_invokes_dismiss_role(tmp_path, monkeypatch):
    monkeypatch.setattr(RE, "_shared_dir", lambda port: tmp_path)
    dismissed: list[str] = []

    def fake_dismiss_role(*, project_port, role_name, reason=None, caller=None):
        dismissed.append(role_name)
        return {"name": role_name}

    with patch("minions.lifecycle.role.dismiss_role", fake_dismiss_role):
        res = RE.apply_dismiss(
            project_port=39999,
            role_name="expert-idle",
            evidence_refs=["auto:starvation:expert-idle"],
            reason="t",
            dry_run=False,
        )
    assert dismissed == ["expert-idle"]
    assert res.roles_out == []
    assert any("dismissed expert-idle" in n for n in res.notes)


# ---------------------------------------------------------------------------
# Apply: live path with monkeypatched spawn/dismiss
# ---------------------------------------------------------------------------


def test_apply_split_invokes_spawn_then_dismiss(tmp_path, monkeypatch):
    monkeypatch.setattr(RE, "_shared_dir", lambda port: tmp_path)
    spawn_calls: list[dict] = []
    dismiss_calls: list[str] = []

    def fake_register_expert(**kwargs):
        spawn_calls.append(kwargs)
        return {"name": kwargs["name"]}

    def fake_dismiss_role(*, project_port, role_name, reason=None, caller=None):
        dismiss_calls.append(role_name)
        return {"name": role_name}

    with (
        patch("minions.lifecycle.role.register_expert", fake_register_expert),
        patch("minions.lifecycle.role.dismiss_role", fake_dismiss_role),
    ):
        res = RE.apply_split(
            project_port=39999,
            source_role="coder",
            into_specs=[
                {"name": "coder-a", "charter": "alpha", "pitfalls": "p"},
                {"name": "coder-b", "charter": "beta", "pitfalls": "p"},
            ],
            evidence_refs=["branches/shared/ethics/x.md"],
            reason="test live",
            dry_run=False,
        )
    assert sorted(res.roles_out) == ["coder-a", "coder-b"]
    assert {c["name"] for c in spawn_calls} == {"coder-a", "coder-b"}
    assert dismiss_calls == ["coder"]


def test_apply_split_keeps_source_alive_on_partial_spawn_failure(tmp_path, monkeypatch):
    """If we cannot get >= 2 specialists up, do not dismiss the source."""
    monkeypatch.setattr(RE, "_shared_dir", lambda port: tmp_path)

    def fake_register_expert(**kwargs):
        if kwargs["name"] == "coder-a":
            return {"name": "coder-a"}
        raise RuntimeError("eacn down")

    dismissed: list[str] = []

    def fake_dismiss(*, project_port, role_name, reason=None, caller=None):
        dismissed.append(role_name)
        return {}

    with (
        patch("minions.lifecycle.role.register_expert", fake_register_expert),
        patch("minions.lifecycle.role.dismiss_role", fake_dismiss),
    ):
        res = RE.apply_split(
            project_port=39999,
            source_role="coder",
            into_specs=[
                {"name": "coder-a", "charter": "x", "pitfalls": "p"},
                {"name": "coder-b", "charter": "y", "pitfalls": "p"},
            ],
            evidence_refs=["branches/shared/ethics/x.md"],
            reason="t",
            dry_run=False,
        )
    # Only one specialist came up, so source coder must stay alive.
    assert dismissed == []
    assert res.roles_out == ["coder-a"]
    assert any("kept source role alive" in n for n in res.notes)
