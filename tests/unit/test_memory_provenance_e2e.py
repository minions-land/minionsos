"""End-to-end tests for the three core Memory-mechanism claims (V23.0).

These tests verify the *full chains* the earlier code audit flagged as
"implemented but unverified end-to-end":

1. Cross-layer provenance — a reel_ref written at Draft-append time is
   carried into the Book page on ingest, so "what came from where" is
   traceable across Reel → Draft → Book. (NOT a paper claim; an internal
   auditability guarantee.)

2. Cold-start context reconstruction — after a compact/wake, a role
   rebuilds working context from book/hot.md + mos_draft_relevant without
   needing the lost transcript.

3. Contradiction audit loop — mos_book_ingest detects a conflicting claim
   against an existing page and emits a contradiction page that Ethics can
   read as its audit feed.

The fixture mirrors test_memory_e2e.py: it monkeypatches the path helpers
and the publish pipeline so the whole stack runs against tmp_path with no
git or network.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minions.tools import book, draft


@pytest.fixture
def project_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Simulated project env: path helpers + publish pipeline against tmp_path."""
    port = 9988
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))
    monkeypatch.setenv("MINIONS_ROLE_NAME", "ethics")

    project_root = tmp_path / f"project_{port}"
    shared = project_root / "branches" / "shared"
    for sub in ("draft", "book", "ethics", "expert"):
        (shared / sub).mkdir(parents=True, exist_ok=True)

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

    for mod in (draft, book):
        monkeypatch.setattr(mod, "project_shared_subdir", _shared_subdir, raising=False)
        monkeypatch.setattr(mod, "project_shared_draft_json", _shared_draft_json, raising=False)
    monkeypatch.setattr(book, "project_state_dir", _state_dir, raising=False)
    monkeypatch.setattr(book, "project_workspace_root", _workspace_root, raising=False)
    monkeypatch.setattr(book, "project_shared_workspace", _shared_workspace, raising=False)

    def _fake_publish(*, role, src_path, dst_subpath, commit_message, port=None, **kwargs):
        dst = _shared_workspace(port or 9988) / dst_subpath
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(Path(src_path).read_text(encoding="utf-8"), encoding="utf-8")
        return {"port": port, "role": role, "dst_path": dst_subpath, "commit_sha": "deadbeef"}

    def _fake_publish_files(*, role, files, commit_message, port=None, **kwargs):
        for entry in files:
            _fake_publish(
                role=role,
                src_path=entry["src_path"],
                dst_subpath=entry["dst_subpath"],
                commit_message=commit_message,
                port=port,
            )
        return {"port": port, "role": role, "commit_sha": "deadbeef"}

    monkeypatch.setattr(book, "mos_publish_to_shared", _fake_publish, raising=False)
    monkeypatch.setattr(book, "mos_publish_files_to_shared", _fake_publish_files, raising=False)

    return port, project_root, shared


# ---------------------------------------------------------------------------
# Test 1 — Cross-layer provenance: reel_ref travels Draft → Book
# ---------------------------------------------------------------------------


def test_reel_ref_travels_from_draft_append_to_book_page(project_env, monkeypatch):
    """A reel_ref captured at Draft-append time must reach the Book source page.

    Chain under test:
      1. Expert appends a Draft node while a reel session is active
         (MINIONS_ROLE_NAME + MINIONS_SESSION_ID set) — draft.py auto-injects
         metadata.reel_ref.
      2. Expert publishes an artifact; Ethics ingests it into the Book with the
         SAME reel_ref.
      3. The Book source page frontmatter carries that reel_ref verbatim, so an
         auditor can walk Book page → reel transcript.
    """
    port, _project_root, shared = project_env

    # --- Layer 1: Draft node gets a reel_ref from the active session ----------
    monkeypatch.setenv("MINIONS_ROLE_NAME", "expert")
    monkeypatch.setenv("MINIONS_SESSION_ID", "sess-abc123")

    appended = draft.mos_draft_append(
        [
            {
                "type": "result",
                "text": "ResNet-50 reached 76.1% top-1 on ImageNet in our rerun",
                "confidence": 0.9,
                "support_status": "verified",
            }
        ]
    )
    created = appended.get("created_node_ids") or appended.get("node_ids") or []
    node_id = created[0] if created else None
    assert node_id, f"append did not return a node id: {appended}"

    # Read the node back and confirm the reel_ref was auto-injected.
    stored = draft._load_draft(port)
    node = next(n for n in stored["nodes"] if n["id"] == node_id)
    draft_reel_ref = node.get("metadata", {}).get("reel_ref")
    assert draft_reel_ref == "expert/sess-abc123", (
        f"Draft node reel_ref not auto-injected; got {draft_reel_ref!r}"
    )

    # --- Layer 2 → 3: Ethics ingests the artifact carrying that reel_ref ------
    artifact = shared / "expert" / "resnet-rerun.md"
    artifact.write_text(
        "# ResNet rerun\n\nResNet-50 reached 76.1% top-1 on ImageNet in our rerun.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MINIONS_ROLE_NAME", "ethics")

    result = book.mos_book_ingest(
        src_path=str(artifact),
        source_role="expert",
        source_slug="resnet-rerun",
        title="ResNet rerun",
        summary="ResNet-50 reached 76.1% top-1 on ImageNet.",
        port=port,
        reel_ref=draft_reel_ref,
    )

    # The Book source page must exist and carry the reel_ref in frontmatter.
    page_path = shared / result["book_path"]
    assert page_path.exists(), f"Book source page not written at {page_path}"
    page_text = page_path.read_text(encoding="utf-8")
    assert "expert/sess-abc123" in page_text, (
        "reel_ref did not propagate into the Book source page — the "
        "Draft→Book provenance link is broken"
    )
    # The frontmatter key must be present (not just the value somewhere).
    assert "reel_ref:" in page_text


# ---------------------------------------------------------------------------
# Test 2 — Cold-start context reconstruction (hot.md + draft_relevant)
# ---------------------------------------------------------------------------


def test_cold_start_context_reconstruction(project_env, monkeypatch):
    """After a compact/wake, a role rebuilds context without its lost transcript.

    Chain under test:
      1. During an earlier work cycle, Draft accumulates research nodes and
         Ethics publishes book/hot.md (the ~500-word rolling cache injected at
         every wake).
      2. A role "wakes" with no transcript memory. It reads hot.md
         (mos_book_hot_get) and pushes the current task text through
         mos_draft_relevant.
      3. The reconstructed context surfaces the prior nodes relevant to the
         task — proving the wake-time context is recoverable from durable
         memory alone.
    """
    port, _project_root, _shared = project_env

    # --- Earlier cycle: Draft accumulates research state ----------------------
    monkeypatch.setenv("MINIONS_ROLE_NAME", "expert")
    monkeypatch.setenv("MINIONS_SESSION_ID", "sess-old")
    draft.mos_draft_append(
        [
            {
                "type": "hypothesis",
                "text": "Residual connections enable training of very deep networks",
                "confidence": 0.8,
                "support_status": "tentative",
            },
            {
                "type": "decision",
                "text": "Use ResNet-50 backbone for the depth-scaling experiment",
                "confidence": 0.9,
                "support_status": "verified",
            },
            {
                "type": "dead_end",
                "text": "Plain 34-layer net diverged without residual connections",
                "confidence": 1.0,
                "support_status": "verified",
            },
            {
                "type": "hypothesis",
                "text": "Batch size has little effect on final accuracy here",
                "confidence": 0.5,
                "support_status": "unverified",
            },
        ]
    )

    # Ethics publishes the rolling hot cache for the cycle.
    monkeypatch.setenv("MINIONS_ROLE_NAME", "ethics")
    book.mos_book_hot_update(
        recent_ingests=[
            {"title": "Depth-scaling rerun", "role": "expert", "one-line": "ResNet beats plain net"}
        ],
        active_hypotheses=2,
        recently_verified=["Residual connections train deep nets"],
        unresolved_contradictions=0,
        port=port,
    )

    # --- Cold start: role wakes with no transcript, rebuilds from memory ------
    hot = book.mos_book_hot_get(port=port)
    assert hot["exists"] is True, "hot.md was not published — wake cache missing"
    assert "Depth-scaling rerun" in hot["content"], (
        "hot.md does not carry the recent-activity summary a waking role needs"
    )

    # The role pushes its current task through the Draft relevance index.
    task_text = "continue the residual connection depth scaling experiment on ResNet"
    relevant = draft.mos_draft_relevant(task_text, max_nodes=5)
    surfaced = {n["text"] for n in relevant["relevant_nodes"]}

    # The depth/residual nodes must surface; they are what the role lost.
    assert any("Residual connections" in t for t in surfaced), (
        f"relevance push failed to surface the residual-connection hypothesis: {surfaced}"
    )
    assert any("ResNet-50 backbone" in t for t in surfaced), (
        f"relevance push failed to surface the backbone decision: {surfaced}"
    )
    # The unrelated batch-size hypothesis should rank below the depth nodes
    # (it shares no strong keywords with the task) — confirms ranking, not dump.
    assert relevant["relevant_nodes"][0]["text"] != (
        "Batch size has little effect on final accuracy here"
    ), "irrelevant node ranked first — relevance scoring is not working"


# ---------------------------------------------------------------------------
# Test 3 — Contradiction audit loop (ingest detects conflict, Ethics reads it)
# ---------------------------------------------------------------------------

_POSITIVE_SENTENCE = (
    "The transformer cache can improve latency because repeated retrieval keeps "
    "attention state stable during project wakeups."
)
_NEGATIVE_SENTENCE = (
    "The transformer cache does not improve latency because repeated retrieval "
    "keeps attention state stable during project wakeups."
)


def test_contradiction_audit_loop(project_env, monkeypatch):
    """A conflicting ingest emits a contradiction page Ethics can read as its feed.

    Chain under test:
      1. Ethics ingests an Expert claim ("cache improves latency").
      2. Ethics later ingests a Coder claim that negates it ("cache does NOT
         improve latency").
      3. mos_book_ingest's lexical detector flags the negation-polarity conflict
         and writes book/contradictions/contradiction-<slug>.md.
      4. The contradiction page — Ethics' "primary hallucination audit feed" —
         cites both opposing sources, so the auditor can adjudicate.
    """
    port, _project_root, shared = project_env
    monkeypatch.setenv("MINIONS_ROLE_NAME", "ethics")

    # --- First claim: ingested cleanly, no contradiction yet ------------------
    art_pos = shared / "expert" / "cache-positive.md"
    art_pos.write_text(f"# Cache positive\n\n{_POSITIVE_SENTENCE}\n", encoding="utf-8")
    res_pos = book.mos_book_ingest(
        src_path=str(art_pos),
        source_role="expert",
        source_slug="cache-positive",
        title="Cache improves latency",
        port=port,
    )
    assert res_pos["contradiction_count"] == 0, (
        "first ingest should not contradict anything (empty Book)"
    )

    # --- Second claim: negates the first → contradiction must fire ------------
    art_neg = shared / "expert" / "cache-negative.md"
    art_neg.write_text(f"# Cache negative\n\n{_NEGATIVE_SENTENCE}\n", encoding="utf-8")
    res_neg = book.mos_book_ingest(
        src_path=str(art_neg),
        source_role="coder",
        source_slug="cache-negative",
        title="Cache does not improve latency",
        port=port,
    )

    assert res_neg["contradiction_count"] >= 1, (
        "negation-polarity conflict was NOT detected — the audit feed is blind "
        "to a direct claim reversal"
    )
    contradiction_rel = res_neg["contradiction_path"]
    assert contradiction_rel, "contradiction detected but no page path returned"

    # --- The contradiction page must exist and cite both sources --------------
    page = shared / contradiction_rel
    assert page.exists(), f"contradiction page not written at {page}"
    page_text = page.read_text(encoding="utf-8")
    # Ethics' feed must name both the new and the opposing source so it can
    # walk to each excerpt during adjudication.
    assert "cache-negative" in page_text, "contradiction page omits the new source"
    assert "cache-positive" in page_text, "contradiction page omits the opposing source"
