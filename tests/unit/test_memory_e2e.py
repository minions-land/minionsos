"""End-to-end integration test simulating a complete project lifecycle.

Exercises: identity layer → Draft creation → Decay computation →
Book promotion → Session crystallization → Contradiction detection.

This is the "simulate a project test" that proves all memory mechanisms
work together coherently in the new naming.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from minions import identity
from minions.tools import book, draft


@pytest.fixture
def project_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Set up a complete simulated project environment with identity."""
    port = 9999
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))
    monkeypatch.setenv("MINIONS_ROLE_NAME", "ethics")
    monkeypatch.setenv("MINIONS_IDENTITY_DIR", str(tmp_path / "identity"))

    project_root = tmp_path / f"project_{port}"
    branches = project_root / "branches"
    shared = branches / "shared"
    workspace = branches / "ethics"
    state = project_root / "state"
    events = project_root / "events"
    for path in (shared, workspace, state, events):
        path.mkdir(parents=True, exist_ok=True)

    def _shared_subdir(p: int, subdir: str) -> Path:
        target = tmp_path / f"project_{p}" / "branches" / "shared" / subdir
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _shared_draft_json(p: int) -> Path:
        return _shared_subdir(p, "draft") / "draft.json"

    def _state_dir(p: int) -> Path:
        target = tmp_path / f"project_{p}" / "state"
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _workspace_root(p: int) -> Path:
        return tmp_path / f"project_{p}"

    def _shared_workspace(p: int) -> Path:
        return _shared_subdir(p, "")

    monkeypatch.setattr(draft, "project_shared_subdir", _shared_subdir)
    monkeypatch.setattr(draft, "project_shared_draft_json", _shared_draft_json)
    monkeypatch.setattr(book, "project_shared_subdir", _shared_subdir)
    monkeypatch.setattr(book, "project_shared_draft_json", _shared_draft_json)
    monkeypatch.setattr(book, "project_state_dir", _state_dir)
    monkeypatch.setattr(book, "project_workspace_root", _workspace_root)
    monkeypatch.setattr(book, "project_shared_workspace", _shared_workspace)

    def _fake_publish(*, role, src_path, dst_subpath, commit_message, port=None, **kwargs):
        dst = _shared_workspace(port or 9999) / dst_subpath
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(Path(src_path).read_text(encoding="utf-8"), encoding="utf-8")
        return {
            "port": port,
            "role": role,
            "dst_path": dst_subpath,
            "commit_sha": "deadbeef",
            "branch": "stub",
            "pushed": False,
            "push_branch": None,
        }

    monkeypatch.setattr(book, "mos_publish_to_shared", _fake_publish)

    def _fake_publish_files(*, role, files, commit_message, port=None, **kwargs):
        for entry in files:
            _fake_publish(
                role=role,
                src_path=entry["src_path"],
                dst_subpath=entry["dst_subpath"],
                commit_message=commit_message,
                port=port,
            )
        return {
            "port": port,
            "role": role,
            "dst_paths": [e["dst_subpath"] for e in files],
            "commit_sha": "deadbeef",
            "branch": "stub",
            "pushed": False,
            "push_branch": None,
        }

    monkeypatch.setattr(book, "mos_publish_files_to_shared", _fake_publish_files)

    def _fake_publish_files(*, role, files, commit_message, port=None, **kwargs):
        for entry in files:
            _fake_publish(
                role=role,
                src_path=entry["src_path"],
                dst_subpath=entry["dst_subpath"],
                commit_message=commit_message,
                port=port,
            )
        return {
            "port": port,
            "role": role,
            "dst_paths": [e["dst_subpath"] for e in files],
            "commit_sha": "deadbeef",
            "branch": "stub",
            "pushed": False,
            "push_branch": None,
        }

    monkeypatch.setattr(book, "mos_publish_files_to_shared", _fake_publish_files)

    # Generate identity for this simulated installation.
    identity.generate_identity()
    return port, project_root


def test_full_memory_pipeline_e2e(project_env, tmp_path: Path, monkeypatch):
    """Simulate a complete research session through the full memory stack."""
    port, _ = project_env

    # Step 1: Identity is generated and stable
    fp = identity.load_fingerprint()
    assert len(fp) == 16
    assert all(c in "0123456789abcdef" for c in fp)

    # Step 2: Universal IDs work for all knowledge unit types
    h_uid = identity.make_uid(port=port, content_type="draft", slug="H-001")
    chapter_uid = identity.make_uid(port=port, content_type="chapter", slug="findings")
    dead_end_uid = identity.make_uid(port=port, content_type="dead-end", slug="failed-x")
    assert identity.uid_is_local(h_uid)
    assert identity.parse_uid(chapter_uid)["content_type"] == "chapter"
    assert identity.parse_uid(dead_end_uid)["slug"] == "failed-x"

    # Step 3: Coder agent writes Draft nodes (research process)
    old_iso = (datetime.now(UTC) - timedelta(days=10)).isoformat(timespec="seconds")
    draft_data = {
        "project_port": port,
        "root_question": "Does attention scale to long sequences?",
        "nodes": [
            {
                "id": "H-001",
                "type": "hypothesis",
                "text": "Standard attention has O(n^2) memory cost",
                "confidence": 0.9,
                "support_status": "verified",
                "author_role": "expert-ml",
                "created_at": old_iso,
                "evidence_tag": "exp-001",
            },
            {
                "id": "I-001",
                "type": "insight",
                "text": "Linear attention reduces memory to O(n) via low-rank decomposition",
                "confidence": 0.85,
                "support_status": "verified",
                "author_role": "expert-ml",
                "created_at": old_iso,
            },
            {
                "id": "DEAD-001",
                "type": "dead_end",
                "text": "Naive sparsity patterns hurt accuracy below 0.5 sparsity",
                "confidence": 1.0,
                "support_status": "verified",
                "author_role": "coder",
                "created_at": old_iso,
            },
            {
                "id": "R-001",
                "type": "result",
                "text": "Linear attention experiment matched dense at 4x speedup",
                "confidence": 0.95,
                "support_status": "verified",
                "author_role": "coder",
                "created_at": old_iso,
            },
        ],
        "edges": [
            {"from_id": "R-001", "to_id": "I-001", "relation": "supports", "strength": 0.9},
            {"from_id": "H-001", "to_id": "I-001", "relation": "supports", "strength": 0.8},
        ],
    }
    draft_path = draft._draft_path(port)
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(json.dumps(draft_data), encoding="utf-8")

    # Step 4: Noter computes decay sidecar
    decay_result = draft.mos_draft_decay_compute()
    assert decay_result["node_count"] == 4
    assert Path(decay_result["path"]).exists()

    # Step 5: Summary surfaces decay info to all roles
    summary = draft.mos_draft_summary()
    assert summary["total_nodes"] == 4
    assert summary["nodes_by_status"]["verified"] == 4
    assert "decay" in summary
    assert summary["decay"]["node_count"] == 4

    # Step 6: Noter promotes verified knowledge to durable Book pages
    promote_result = book.mos_book_promote_verified(port=port)
    assert promote_result["promoted_count"] >= 1, (
        f"Expected at least 1 promotion, got {promote_result['promoted_count']}"
    )
    promoted_node_ids = {p["node_id"] for p in promote_result["promoted"]}
    # I-001 has 2 supports edges, so it qualifies; R-001 has 1 supports
    # so doesn't meet the min_supporting_edges=2 threshold.
    assert "I-001" in promoted_node_ids

    # Verify the promoted page contains verbatim content with UID-ready citations
    book_root = book._book_root(port)
    promoted_pages = list((book_root / "sources").glob("ethics-promoted-*.md"))
    assert len(promoted_pages) >= 1
    body = promoted_pages[0].read_text(encoding="utf-8")
    assert "Linear attention" in body
    assert "[I-001]" in body
    assert "Citations" in body

    # Step 7: Idempotent — second promotion attempt does nothing
    second = book.mos_book_promote_verified(port=port)
    assert second["promoted_count"] == 0

    # Step 8: Crystallize Coder's session window into a verbatim Book page
    crystallize_result = book.mos_book_crystallize_session(
        role="coder",
        window_minutes=43200,
        port=port,  # 30 days window catches all
    )
    assert "DEAD-001" in crystallize_result["cited_node_ids"]
    assert "R-001" in crystallize_result["cited_node_ids"]
    # Expert nodes should NOT appear (different role)
    assert "I-001" not in crystallize_result["cited_node_ids"]


def test_book_dead_end_promotion(project_env):
    """Verify that dead_end nodes are promoted (ARA's first-class dead ends)."""
    port, _ = project_env

    old_iso = (datetime.now(UTC) - timedelta(days=10)).isoformat(timespec="seconds")
    draft_data = {
        "project_port": port,
        "root_question": "test",
        "nodes": [
            {
                "id": "DEAD-001",
                "type": "dead_end",
                "text": "Tried sparse attention with random patterns - accuracy dropped 15%",
                "confidence": 1.0,
                "support_status": "verified",
                "author_role": "coder",
                "created_at": old_iso,
            },
        ],
        "edges": [
            {"from_id": "R-001", "to_id": "DEAD-001", "relation": "supports", "strength": 0.9},
            {"from_id": "R-002", "to_id": "DEAD-001", "relation": "supports", "strength": 0.9},
        ],
    }
    draft_path = draft._draft_path(port)
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(json.dumps(draft_data), encoding="utf-8")

    # Dead-ends are first-class citizens per ARA's design — they should be
    # promoted to durable Book pages so other projects can avoid the failed path.
    result = book.mos_book_promote_verified(port=port)
    assert result["promoted_count"] == 1
    assert result["promoted"][0]["node_id"] == "DEAD-001"
    assert result["promoted"][0]["type"] == "dead_end"


def test_identity_uid_format_consistency(project_env):
    """UIDs should be parseable and round-trip through the system."""
    port, _ = project_env

    fp = identity.load_fingerprint()
    proj_fp = identity.project_fingerprint(port)

    # All four content types we care about
    for content_type in ("draft", "chapter", "dead-end", "book"):
        uid = identity.make_uid(port=port, content_type=content_type, slug="test")
        parsed = identity.parse_uid(uid)
        assert parsed is not None
        assert parsed["owner"] == fp
        assert parsed["project"] == proj_fp
        assert parsed["content_type"] == content_type
        assert identity.uid_is_local(uid)

    # Foreign UIDs are correctly identified as non-local
    foreign = "mos://aaaaaaaaaaaaaaaa/bbbbbbbbbbbbbbbb/chapter/foreign-thing"
    assert not identity.uid_is_local(foreign)
    assert identity.uid_owner(foreign) == "aaaaaaaaaaaaaaaa"


def test_decay_reinforces_with_supports(project_env):
    """A node with many supports edges should decay slower than a lonely node."""
    port, _ = project_env

    # Both nodes 30 days old. H-supported has 3 supports, H-lonely has 0.
    iso = (datetime.now(UTC) - timedelta(days=30)).isoformat(timespec="seconds")
    draft_data = {
        "project_port": port,
        "root_question": "test",
        "nodes": [
            {
                "id": "H-supported",
                "type": "hypothesis",
                "text": "well-supported",
                "confidence": 1.0,
                "support_status": "verified",
                "created_at": iso,
            },
            {
                "id": "H-lonely",
                "type": "hypothesis",
                "text": "no support",
                "confidence": 1.0,
                "support_status": "verified",
                "created_at": iso,
            },
        ],
        "edges": [
            {"from_id": "R-1", "to_id": "H-supported", "relation": "supports"},
            {"from_id": "R-2", "to_id": "H-supported", "relation": "supports"},
            {"from_id": "R-3", "to_id": "H-supported", "relation": "supports"},
        ],
    }
    draft_path = draft._draft_path(port)
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(json.dumps(draft_data), encoding="utf-8")

    draft.mos_draft_decay_compute()
    decay = json.loads(draft._decay_path(port).read_text(encoding="utf-8"))
    nodes = decay["nodes"]

    # Reinforcement should noticeably slow decay
    supported_eff = nodes["H-supported"]["effective_confidence"]
    lonely_eff = nodes["H-lonely"]["effective_confidence"]
    assert supported_eff > lonely_eff, (
        f"reinforcement should slow decay: supported={supported_eff} vs lonely={lonely_eff}"
    )
