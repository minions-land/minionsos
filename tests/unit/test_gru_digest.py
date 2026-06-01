"""Tests for the Gru periodic digest (C+D)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from minions.gru import digest as digest_mod


@pytest.fixture()
def project_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Create a minimal project_<port>/ scaffolding with events/ and shared/draft/."""
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path))
    port = 39998
    proot = tmp_path / f"project_{port}"
    events = proot / "events"
    draft_dir = proot / "branches" / "main" / "draft"
    governance = proot / "branches" / "main" / "governance"
    for d in (events, draft_dir, governance):
        d.mkdir(parents=True, exist_ok=True)
    return {
        "port": port,  # type: ignore[dict-item]
        "events": events,
        "draft_dir": draft_dir,
        "governance": governance,
    }


def _write_events(events_dir: Path, agent: str, lines: list[dict]) -> None:
    p = events_dir / f"{agent}.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for line in lines:
            fh.write(json.dumps(line) + "\n")


def _write_draft(draft_dir: Path, nodes: list[dict]) -> None:
    (draft_dir / "draft.json").write_text(
        json.dumps({"project_port": 0, "root_question": "", "nodes": nodes, "edges": []}),
        encoding="utf-8",
    )


def test_collect_digest_with_no_files_is_empty_zero(project_dirs) -> None:
    port = int(project_dirs["port"])  # type: ignore[arg-type]
    snapshot = digest_mod.collect_project_digest(port, role_names=["coder"], window_seconds=270)
    assert snapshot.port == port
    assert len(snapshot.rows) == 1
    row = snapshot.rows[0]
    assert row.real_events == 0
    assert row.keepalive_events == 0
    assert row.draft_growth == 0
    assert row.ratio is None
    assert snapshot.anomalies == []


def test_collect_digest_counts_events_and_drafts_in_window(project_dirs) -> None:
    port = int(project_dirs["port"])  # type: ignore[arg-type]
    now = datetime(2026, 5, 24, 15, 30, tzinfo=UTC)
    in_window = (now - timedelta(seconds=60)).isoformat()
    out_of_window = (now - timedelta(seconds=600)).isoformat()
    _write_events(
        project_dirs["events"],
        "coder",
        [
            {"ingested_at": in_window, "event": {"type": "task_broadcast"}},
            {"ingested_at": in_window, "event": {"type": "direct_message"}},
            {"ingested_at": in_window, "event": {"type": "cache_keepalive"}},
            {"ingested_at": out_of_window, "event": {"type": "task_broadcast"}},
        ],
    )
    _write_draft(
        project_dirs["draft_dir"],
        [
            {"id": "x1", "author_role": "coder", "created_at": in_window},
            {"id": "x2", "author_role": "coder", "created_at": out_of_window},
            {"id": "x3", "author_role": "ethics", "created_at": in_window},
        ],
    )
    snap = digest_mod.collect_project_digest(
        port, role_names=["coder"], window_seconds=270, now=now
    )
    row = snap.rows[0]
    assert row.real_events == 2  # 2 in-window non-keepalive
    assert row.keepalive_events == 1
    assert row.draft_growth == 1  # only x1 (x3 is ethics, x2 out of window)
    assert row.ratio == pytest.approx(0.5)
    assert snap.anomalies == []  # 2 < anomaly_min_events (default 3)


def test_anomaly_when_real_events_with_zero_drafts(project_dirs) -> None:
    """The motivating case: ethics-style role gets 5 events, writes 0 Draft."""
    port = int(project_dirs["port"])  # type: ignore[arg-type]
    now = datetime(2026, 5, 24, 15, 30, tzinfo=UTC)
    in_window = (now - timedelta(seconds=60)).isoformat()
    _write_events(
        project_dirs["events"],
        "ethics",
        [{"ingested_at": in_window, "event": {"type": f"adjudication_task_{i}"}} for i in range(5)],
    )
    _write_draft(project_dirs["draft_dir"], [])
    snap = digest_mod.collect_project_digest(
        port, role_names=["ethics"], window_seconds=270, now=now
    )
    assert snap.rows[0].real_events == 5
    assert snap.rows[0].draft_growth == 0
    assert len(snap.anomalies) == 1
    assert "ethics" in snap.anomalies[0]


def test_below_threshold_does_not_anomaly(project_dirs) -> None:
    port = int(project_dirs["port"])  # type: ignore[arg-type]
    now = datetime(2026, 5, 24, 15, 30, tzinfo=UTC)
    in_window = (now - timedelta(seconds=60)).isoformat()
    _write_events(
        project_dirs["events"],
        "ethics",
        [{"ingested_at": in_window, "event": {"type": "task_broadcast"}}],
    )
    _write_draft(project_dirs["draft_dir"], [])
    snap = digest_mod.collect_project_digest(
        port, role_names=["ethics"], window_seconds=270, now=now, anomaly_min_events=3
    )
    assert snap.rows[0].real_events == 1
    assert snap.anomalies == []  # 1 < 3


def test_render_markdown_contains_table_and_anomalies(project_dirs) -> None:
    port = int(project_dirs["port"])  # type: ignore[arg-type]
    rows = [
        digest_mod.RoleDigestRow(
            role="coder", real_events=4, keepalive_events=2, draft_growth=2, ratio=0.5
        ),
        digest_mod.RoleDigestRow(
            role="ethics", real_events=5, keepalive_events=0, draft_growth=0, ratio=0.0
        ),
    ]
    snap = digest_mod.ProjectDigest(
        port=port,
        window_start_iso="2026-05-24T15:25:00+00:00",
        window_end_iso="2026-05-24T15:30:00+00:00",
        rows=rows,
        anomalies=["role='ethics': received 5 real events but wrote 0 Draft nodes"],
    )
    md = digest_mod.render_digest_markdown(snap)
    assert f"port {port}" in md
    assert "| coder |" in md
    assert "| ethics |" in md
    assert "0.50" in md  # coder ratio
    assert "## Anomalies" in md
    assert "5 real events but wrote 0" in md


def test_publish_digest_writes_file(project_dirs) -> None:
    port = int(project_dirs["port"])  # type: ignore[arg-type]
    snap = digest_mod.ProjectDigest(
        port=port,
        window_start_iso="2026-05-24T15:25:00+00:00",
        window_end_iso="2026-05-24T15:30:00+00:00",
        rows=[],
        anomalies=[],
    )
    result = digest_mod.publish_digest(snap, notify_anomalies=False)
    assert result["path"]
    out_path = Path(result["path"])
    assert out_path.is_file()
    content = out_path.read_text(encoding="utf-8")
    assert "port" in content


def test_publish_digest_handles_iso_with_colons_in_filename(project_dirs) -> None:
    port = int(project_dirs["port"])  # type: ignore[arg-type]
    snap = digest_mod.ProjectDigest(
        port=port,
        window_start_iso="2026-05-24T15:25:00+00:00",
        window_end_iso="2026-05-24T15:30:00+00:00",
        rows=[],
        anomalies=[],
    )
    result = digest_mod.publish_digest(snap, notify_anomalies=False)
    out_path = Path(result["path"])
    # Colons not allowed on most file systems → must be replaced.
    assert ":" not in out_path.name
    assert out_path.name.endswith(".md")
