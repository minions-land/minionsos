"""Unit tests for the LLM-Wiki-V2 memory enhancements.

Covers:
- Confidence decay sidecar (mos_draft_decay_compute + summary join)
- Knowledge promotion (mos_book_promote_verified)
- Session crystallization (mos_book_crystallize_session)
- Contradiction statistical signals
- Atlas 2-hop expansion

Each test uses a tmp project workspace and stubs out mos_publish_to_shared
so commits don't actually run — we only verify the staging output and the
in-memory return values.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from minions.tools import book, draft, shelf


@pytest.fixture(autouse=True)
def _project_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    port = 9999
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))
    monkeypatch.setenv("MINIONS_ROLE_NAME", "noter")

    project_root = tmp_path / f"project_{port}"
    branches = project_root / "branches"
    shared = branches / "shared"
    workspace = branches / "noter"
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

    # Stub publish: write the staged file directly into the destination tree.
    # dst_subpath is already prefixed with "book/" by book._publish_file,
    # so we resolve it relative to the shared root (which is shared_subdir(p, "")).
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
    return port, project_root


def _write_draft(port: int, nodes: list[dict], edges: list[dict] | None = None) -> None:
    from minions.tools.draft import _draft_path

    path = _draft_path(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "project_port": port,
        "root_question": "test",
        "nodes": nodes,
        "edges": edges or [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestDecaySidecar:
    def test_decay_compute_writes_sidecar_with_effective_confidence(self):
        port = 9999
        old_iso = (datetime.now(UTC) - timedelta(days=60)).isoformat(timespec="seconds")
        fresh_iso = datetime.now(UTC).isoformat(timespec="seconds")
        _write_draft(
            port,
            nodes=[
                {
                    "id": "H-001",
                    "type": "hypothesis",
                    "text": "old unverified hypothesis",
                    "confidence": 1.0,
                    "created_at": old_iso,
                    "support_status": "unverified",
                },
                {
                    "id": "D-001",
                    "type": "decision",
                    "text": "fresh decision",
                    "confidence": 1.0,
                    "created_at": fresh_iso,
                    "support_status": "verified",
                },
            ],
            edges=[],
        )
        result = draft.mos_draft_decay_compute()
        assert result["node_count"] == 2

        sidecar = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
        nodes = sidecar["nodes"]
        # Old hypothesis with 30d half-life and 60d age should be ~0.25.
        assert nodes["H-001"]["effective_confidence"] < 0.5
        # Fresh decision is essentially full confidence.
        assert nodes["D-001"]["effective_confidence"] > 0.95

    def test_supports_edge_reinforces_confidence(self):
        port = 9999
        old_iso = (datetime.now(UTC) - timedelta(days=30)).isoformat(timespec="seconds")
        _write_draft(
            port,
            nodes=[
                {
                    "id": "H-001",
                    "type": "hypothesis",
                    "text": "supported claim",
                    "confidence": 1.0,
                    "created_at": old_iso,
                    "support_status": "tentative",
                },
                {
                    "id": "H-002",
                    "type": "hypothesis",
                    "text": "lonely claim",
                    "confidence": 1.0,
                    "created_at": old_iso,
                    "support_status": "tentative",
                },
            ],
            edges=[
                {"from_id": "R-001", "to_id": "H-001", "relation": "supports"},
                {"from_id": "R-002", "to_id": "H-001", "relation": "supports"},
            ],
        )
        draft.mos_draft_decay_compute()
        from minions.tools.draft import _decay_path

        nodes = json.loads(_decay_path(port).read_text(encoding="utf-8"))["nodes"]
        # H-001 has 2 supports, H-002 has none; same age and type.
        assert nodes["H-001"]["effective_confidence"] > nodes["H-002"]["effective_confidence"]

    def test_summary_joins_decay_view_when_sidecar_exists(self):
        port = 9999
        old_iso = (datetime.now(UTC) - timedelta(days=60)).isoformat(timespec="seconds")
        _write_draft(
            port,
            nodes=[
                {
                    "id": "H-001",
                    "type": "hypothesis",
                    "text": "old",
                    "confidence": 1.0,
                    "created_at": old_iso,
                }
            ],
        )
        draft.mos_draft_decay_compute()
        summary = draft.mos_draft_summary()
        assert "decay" in summary
        assert summary["decay"]["node_count"] == 1
        assert summary["decay"]["most_decayed"][0]["id"] == "H-001"

    def test_summary_omits_decay_when_no_sidecar(self):
        port = 9999
        _write_draft(
            port,
            nodes=[{"id": "H-001", "type": "hypothesis", "text": "x", "confidence": 1.0}],
        )
        summary = draft.mos_draft_summary()
        assert summary.get("decay") == {}


class TestKnowledgePromotion:
    def test_promote_picks_eligible_verified_insight(self):
        port = 9999
        old_iso = (datetime.now(UTC) - timedelta(days=10)).isoformat(timespec="seconds")
        _write_draft(
            port,
            nodes=[
                {
                    "id": "I-001",
                    "type": "insight",
                    "text": "VERBATIM insight body that must appear in the page.",
                    "confidence": 0.9,
                    "created_at": old_iso,
                    "support_status": "verified",
                    "author_role": "expert-foo",
                }
            ],
            edges=[
                {"from_id": "R-001", "to_id": "I-001", "relation": "supports", "strength": 0.9},
                {"from_id": "R-002", "to_id": "I-001", "relation": "supports", "strength": 0.8},
            ],
        )
        result = book.mos_book_promote_verified(port=port)
        assert result["promoted_count"] == 1
        assert result["promoted"][0]["node_id"] == "I-001"

        from minions.tools.book import _book_root

        sources = list((_book_root(port) / "sources").glob("noter-promoted-*.md"))
        assert len(sources) == 1
        body = sources[0].read_text(encoding="utf-8")
        assert "VERBATIM insight body" in body
        assert "[I-001]" in body
        assert "Citations (Draft supports edges)" in body

    def test_promote_skips_unverified_or_too_young(self):
        port = 9999
        fresh_iso = datetime.now(UTC).isoformat(timespec="seconds")
        old_iso = (datetime.now(UTC) - timedelta(days=10)).isoformat(timespec="seconds")
        _write_draft(
            port,
            nodes=[
                {
                    "id": "I-001",
                    "type": "insight",
                    "text": "too young",
                    "created_at": fresh_iso,
                    "support_status": "verified",
                },
                {
                    "id": "I-002",
                    "type": "insight",
                    "text": "not enough supports",
                    "created_at": old_iso,
                    "support_status": "verified",
                },
                {
                    "id": "I-003",
                    "type": "insight",
                    "text": "not verified",
                    "created_at": old_iso,
                    "support_status": "tentative",
                },
            ],
            edges=[
                {"from_id": "R-001", "to_id": "I-002", "relation": "supports"},
            ],
        )
        result = book.mos_book_promote_verified(port=port)
        assert result["promoted_count"] == 0

    def test_promote_idempotent_after_existing_citation(self):
        port = 9999
        old_iso = (datetime.now(UTC) - timedelta(days=10)).isoformat(timespec="seconds")
        _write_draft(
            port,
            nodes=[
                {
                    "id": "I-001",
                    "type": "insight",
                    "text": "claim",
                    "created_at": old_iso,
                    "support_status": "verified",
                }
            ],
            edges=[
                {"from_id": "R-001", "to_id": "I-001", "relation": "supports"},
                {"from_id": "R-002", "to_id": "I-001", "relation": "supports"},
            ],
        )
        first = book.mos_book_promote_verified(port=port)
        assert first["promoted_count"] == 1
        second = book.mos_book_promote_verified(port=port)
        assert second["promoted_count"] == 0


class TestSessionCrystallization:
    def test_crystallize_captures_role_draft_nodes_verbatim(self):
        port = 9999
        recent_iso = (datetime.now(UTC) - timedelta(minutes=5)).isoformat(timespec="seconds")
        old_iso = (datetime.now(UTC) - timedelta(hours=4)).isoformat(timespec="seconds")
        _write_draft(
            port,
            nodes=[
                {
                    "id": "H-001",
                    "type": "hypothesis",
                    "text": "RECENT THOUGHT verbatim",
                    "author_role": "coder",
                    "created_at": recent_iso,
                },
                {
                    "id": "H-002",
                    "type": "hypothesis",
                    "text": "OUT OF WINDOW",
                    "author_role": "coder",
                    "created_at": old_iso,
                },
                {
                    "id": "H-003",
                    "type": "hypothesis",
                    "text": "OTHER ROLE",
                    "author_role": "writer",
                    "created_at": recent_iso,
                },
            ],
        )
        result = book.mos_book_crystallize_session(role="coder", window_minutes=60, port=port)
        assert "H-001" in result["cited_node_ids"]
        assert "H-002" not in result["cited_node_ids"]
        assert "H-003" not in result["cited_node_ids"]

        from minions.tools.book import _book_root

        # book_path is "book/sources/<slug>.md"; _book_root is shared/book.
        rel = result["book_path"].removeprefix("book/")
        path = _book_root(port) / rel
        body = path.read_text(encoding="utf-8")
        assert "RECENT THOUGHT verbatim" in body
        assert "OUT OF WINDOW" not in body
        assert "OTHER ROLE" not in body


class TestContradictionSignals:
    def test_contradiction_page_contains_signals_table(self, tmp_path: Path):
        port = 9999
        from minions.tools.book import _book_root

        sources = _book_root(port) / "sources"
        sources.mkdir(parents=True, exist_ok=True)
        old_iso = (datetime.now(UTC) - timedelta(days=4)).isoformat(timespec="seconds")
        (sources / "expert-foo.md").write_text(
            "---\n"
            "type: source\n"
            f'date_ingested: "{old_iso}"\n'
            "page_kind: source\n"
            "---\n\n"
            "Existing source claims attention is NOT helpful for long sequences in this regime.\n",
            encoding="utf-8",
        )

        # Stage a candidate body and contradictions, then call the renderer
        # directly to verify the signals block is present.
        contradictions = [
            {
                "opposing_page": "book/sources/expert-foo.md",
                "excerpts": {
                    "new": "We claim attention IS helpful for long sequences in this regime.",
                    "opposing": "attention is NOT helpful for long sequences in this regime.",
                },
                "shared_terms": ["attention", "sequences", "regime"],
                "new_source": "coder-bar",
                "new_source_role": "coder",
            }
        ]
        page = book._render_contradiction_page(
            "coder-bar",
            contradictions,
            "coder",
            datetime.now(UTC).isoformat(timespec="seconds"),
            port=port,
        )
        assert "## Statistical signals" in page
        assert "opposing_age_d" in page
        assert "expert-foo.md" in page
        # The signals block must be descriptive only — no row labels or
        # verdict tokens drawn from Ethics' five-choice set.
        forbidden = (
            "resolved-in-favor-of-new",
            "resolved-in-favor-of-existing",
            "needs-experiment",
            "out-of-scope",
            "both-correct-different-scope",
        )
        for token in forbidden:
            assert token not in page


class TestShelfTwoHop:
    def test_one_hop_neighbour_surfaces_at_lower_score(self, tmp_path, monkeypatch):
        # Override shelf global path to tmp.
        global_path = tmp_path / "shelf-global.json"
        global_path.write_text(
            json.dumps(
                {
                    "projects": {"41001": {"port": 41001, "nodes": 2, "links": 1}},
                    "nodes": [
                        {"id": "p41001_a", "label": "transformer", "project_port": 41001},
                        {
                            "id": "p41001_b",
                            "label": "self-attention layer",
                            "project_port": 41001,
                        },
                    ],
                    "links": [
                        {
                            "source": "p41001_a",
                            "target": "p41001_b",
                            "project_port": 41001,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(shelf, "_shelf_path", lambda: global_path)
        result = shelf.mos_shelf_query("transformer")
        assert result["total"] == 2
        labels = {(m["label"], m["via"]) for m in result["matches"]}
        assert ("transformer", "direct") in labels
        assert ("self-attention layer", "1-hop") in labels
        # 1-hop score is 0.4 of direct score.
        direct = next(m for m in result["matches"] if m["via"] == "direct")
        hop = next(m for m in result["matches"] if m["via"] == "1-hop")
        assert hop["score"] == pytest.approx(direct["score"] * 0.4, rel=1e-3)
