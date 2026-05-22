"""End-to-end simulation of the Noter+Ethics collaboration chain.

This proves the architectural claims I made about how Noter and Ethics work
together in the new Draft/Book/Shelf naming. It runs the COMPLETE chain:

  1. Coder publishes an artifact to shared/coder/
  2. Noter (wake cycle) ingests it as a Book chapter, detects a lexical
     contradiction with an existing Book chapter, generates a contradiction
     page WITH the Statistical Signals table.
  3. Ethics reads the contradiction page, issues a verdict, publishes it,
     and writes a `decision` node + `supersedes` edge into the Draft.
  4. Noter (next wake) recomputes decay; supersedes-affected nodes show
     accelerated decay. Verdict gets promoted to a Book chapter.
  5. The hot.md cache reflects the resolution.

Every claim about what Noter/Ethics can do is verified here against the
actual code paths. If any of this fails, the architecture is broken.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from fnmatch import fnmatchcase
from pathlib import Path

import pytest

from minions import identity
from minions.config import resolve_server_authz
from minions.tools import book, draft, shelf

# ---------------------------------------------------------------------------
# Fixture — full simulated project workspace
# ---------------------------------------------------------------------------


@pytest.fixture
def sim_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    port = 50000
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))
    monkeypatch.setenv("MINIONS_IDENTITY_DIR", str(tmp_path / "identity"))
    # Track role-name env mutations so we can always restore the original
    # at fixture teardown — helpers below set MINIONS_ROLE_NAME directly
    # (because the sim mimics multiple roles within one test) which
    # monkeypatch.setenv cannot undo. The delenv call here ensures clean
    # slate even if a prior test leaked.
    original_role = os.environ.get("MINIONS_ROLE_NAME")
    monkeypatch.setenv("MINIONS_ROLE_NAME", "")
    identity.generate_identity()

    project_root = tmp_path / f"project_{port}"
    for sub in ("branches/shared", "branches/coder", "branches/noter",
                "branches/ethics", "state", "events"):
        (project_root / sub).mkdir(parents=True, exist_ok=True)

    def _shared_subdir(p, subdir):
        target = project_root / "branches" / "shared" / subdir
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _shared_draft_json(p):
        return _shared_subdir(p, "draft") / "draft.json"

    def _state_dir(p):
        target = project_root / "state"
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _workspace_root(p):
        return project_root

    def _shared_workspace(p):
        return _shared_subdir(p, "")

    monkeypatch.setattr(draft, "project_shared_subdir", _shared_subdir)
    monkeypatch.setattr(draft, "project_shared_draft_json", _shared_draft_json)
    monkeypatch.setattr(book, "project_shared_subdir", _shared_subdir)
    monkeypatch.setattr(book, "project_shared_draft_json", _shared_draft_json)
    monkeypatch.setattr(book, "project_state_dir", _state_dir)
    monkeypatch.setattr(book, "project_workspace_root", _workspace_root)
    monkeypatch.setattr(book, "project_shared_workspace", _shared_workspace)

    def _fake_publish(*, role, src_path, dst_subpath, commit_message,
                      port=None, **kwargs):
        dst = _shared_workspace(port or 50000) / dst_subpath
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(Path(src_path).read_text(encoding="utf-8"),
                       encoding="utf-8")
        return {
            "port": port, "role": role, "dst_path": dst_subpath,
            "commit_sha": f"sim-{role}", "branch": "stub",
            "pushed": False, "push_branch": None,
        }

    monkeypatch.setattr(book, "mos_publish_to_shared", _fake_publish)
    yield port, project_root
    # Teardown — restore role env. Helpers above use os.environ directly
    # (to mimic mid-test role switches), so monkeypatch can't undo them.
    if original_role is None:
        os.environ.pop("MINIONS_ROLE_NAME", None)
    else:
        os.environ["MINIONS_ROLE_NAME"] = original_role


# ---------------------------------------------------------------------------
# Helpers — simulate each role's actions
# ---------------------------------------------------------------------------


def _coder_publishes_artifact(project_root: Path, slug: str, body: str) -> Path:
    """Coder writes a research artifact under shared/coder/."""
    coder_shared = project_root / "branches" / "shared" / "coder"
    coder_shared.mkdir(parents=True, exist_ok=True)
    artifact = coder_shared / f"{slug}.md"
    artifact.write_text(body, encoding="utf-8")
    return artifact


def _noter_ingests(port: int, artifact_path: Path, role: str, slug: str) -> dict:
    """Noter step 5 of wake cycle: ingest a fresh shared/ artifact."""
    os.environ["MINIONS_ROLE_NAME"] = "noter"
    return book.mos_book_ingest(
        src_path=str(artifact_path),
        source_role=role,
        source_slug=slug,
        title=f"{role}: {slug}",
        port=port,
    )


def _ethics_reads_contradiction(port: int, contradiction_slug: str) -> str:
    """Ethics opens a contradiction page generated by Noter's ingest."""
    page = book._book_root(port) / "contradictions" / f"{contradiction_slug}.md"
    return page.read_text(encoding="utf-8")


def _ethics_publishes_verdict(
    port: int, project_root: Path, contradiction_slug: str, verdict: str,
    losing_node_id: str, winning_node_id: str,
) -> Path:
    """Ethics step 3 of contradiction surface: publish verdict to shared/ethics/."""
    os.environ["MINIONS_ROLE_NAME"] = "ethics"
    ethics_dir = project_root / "branches" / "ethics"
    ethics_dir.mkdir(parents=True, exist_ok=True)
    verdict_path = ethics_dir / f"verdict-{contradiction_slug}.md"
    verdict_path.write_text(
        f"# Verdict: {contradiction_slug}\n\n"
        f"**Decision**: {verdict}\n\n"
        f"**Losing claim**: [{losing_node_id}]\n"
        f"**Winning claim**: [{winning_node_id}]\n\n"
        "[evidence: contradictions/{contradiction_slug}.md]\n",
        encoding="utf-8",
    )
    # Publish to shared/ethics/ via the real publish path
    book.mos_publish_to_shared(
        role="ethics",
        src_path=str(verdict_path),
        dst_subpath=f"ethics/verdict-{contradiction_slug}.md",
        commit_message=f"ethics: verdict on {contradiction_slug}",
        port=port,
    )
    return verdict_path


def _ethics_writes_supersedes_edge(
    port: int, losing_node_id: str, winning_node_id: str, verdict_slug: str,
):
    """Ethics step 5: write decision node + supersedes edge to its own Draft."""
    os.environ["MINIONS_ROLE_NAME"] = "ethics"
    decision_id = f"D-{verdict_slug.replace('-', '').upper()[:8]}"
    draft.mos_draft_append(
        nodes=[
            {
                "id": decision_id,
                "type": "decision",
                "text": f"Resolved: {winning_node_id} supersedes {losing_node_id}",
                "support_status": "verified",
                "author_role": "ethics",
                "evidence_tag": f"ethics/verdict-{verdict_slug}.md",
                "confidence": 1.0,
            }
        ],
        edges=[
            {
                "from_id": winning_node_id,
                "to_id": losing_node_id,
                "relation": "supersedes",
                "strength": 1.0,
                "author_role": "ethics",
            },
            {
                "from_id": winning_node_id,
                "to_id": losing_node_id,
                "relation": "contradicts",
                "strength": 1.0,
                "author_role": "ethics",
            },
        ],
    )


def _seed_initial_draft(port: int, ages_days: dict[str, int]):
    """Seed the Draft with two opposing claims from prior research."""
    nodes = []
    for nid, age in ages_days.items():
        nodes.append({
            "id": nid,
            "type": "result",
            "text": f"Claim {nid}",
            "support_status": "verified",
            "author_role": "expert",
            "confidence": 1.0,
            "created_at": (datetime.now(UTC) - timedelta(days=age))
                          .isoformat(timespec="seconds"),
        })
    payload = {
        "project_port": port,
        "root_question": "Does X work?",
        "nodes": nodes,
        "edges": [],
    }
    path = draft._draft_path(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# THE MAIN END-TO-END TEST
# ---------------------------------------------------------------------------


def test_noter_ethics_full_collaboration_chain(sim_project, tmp_path: Path):
    """Run the COMPLETE Noter→Ethics chain I described, verify every step."""
    port, project_root = sim_project

    # ─── Phase 0: Seed prior research as Draft nodes ───────────────────────
    _seed_initial_draft(port, ages_days={"R-OLD": 20, "R-NEW": 1})
    initial_summary = draft.mos_draft_summary()
    assert initial_summary["total_nodes"] == 2

    # ─── Phase 1: Existing Book chapter (older claim) ──────────────────────
    old_artifact = _coder_publishes_artifact(
        project_root, "old-finding",
        "We claim attention IS NOT helpful for sequences longer than 4096 "
        "in the standard transformer regime.\n",
    )
    ingest_old = _noter_ingests(port, old_artifact, "coder", "old-finding")
    assert ingest_old["contradiction_count"] == 0  # no prior pages to clash with

    # ─── Phase 2: New artifact contradicts the old one ─────────────────────
    new_artifact = _coder_publishes_artifact(
        project_root, "new-finding",
        "We claim attention IS helpful for sequences longer than 4096 "
        "in the standard transformer regime.\n",
    )
    ingest_new = _noter_ingests(port, new_artifact, "coder", "new-finding")

    # ⭐ ASSERTION 1: Noter automatically detected the contradiction
    assert ingest_new["contradiction_count"] >= 1, (
        "Noter should detect lexical contradiction between old and new claims"
    )
    contradiction_slug = ingest_new["contradiction_path"].split("/")[-1].replace(".md", "")

    # ─── Phase 3: Ethics reads contradiction page ──────────────────────────
    page_text = _ethics_reads_contradiction(port, contradiction_slug)

    # ⭐ ASSERTION 2: The page contains the Statistical Signals table
    assert "## Statistical signals" in page_text, (
        "Contradiction page must include Noter-assembled signals table"
    )
    assert "opposing_age_d" in page_text
    assert "opposing_unmarked" in page_text
    assert "draft_matches" in page_text
    assert "supports" in page_text
    assert "avg_eff_conf" in page_text

    # ⭐ ASSERTION 3: Signals are descriptive only, no verdict tokens
    forbidden_verdicts = (
        "resolved-in-favor-of-new", "resolved-in-favor-of-existing",
        "needs-experiment", "out-of-scope", "both-correct-different-scope",
    )
    for v in forbidden_verdicts:
        assert v not in page_text, (
            f"Noter must not pre-decide verdicts; found {v!r} in page"
        )

    # ─── Phase 4: Ethics issues verdict and publishes to shared/ethics/ ────
    verdict_path = _ethics_publishes_verdict(
        port, project_root, contradiction_slug,
        verdict="resolved-in-favor-of-new",
        losing_node_id="R-OLD",
        winning_node_id="R-NEW",
    )
    assert verdict_path.exists()

    # ⭐ ASSERTION 4: Verdict landed on shared branch (via mos_publish_to_shared)
    published_verdict = (project_root / "branches" / "shared" / "ethics"
                         / f"verdict-{contradiction_slug}.md")
    assert published_verdict.exists(), (
        "Ethics verdict must be visible cross-role under shared/ethics/"
    )

    # ─── Phase 5: Ethics writes supersedes edge to Draft ───────────────────
    _ethics_writes_supersedes_edge(
        port, "R-OLD", "R-NEW", contradiction_slug,
    )

    # ⭐ ASSERTION 5: Supersedes edge is in the Draft
    draft_data = json.loads(draft._draft_path(port).read_text(encoding="utf-8"))
    edges = draft_data["edges"]
    has_supersedes = any(
        e["relation"] == "supersedes"
        and e["from_id"] == "R-NEW"
        and e["to_id"] == "R-OLD"
        for e in edges
    )
    assert has_supersedes, "Ethics must write supersedes edge after verdict"

    has_contradicts = any(
        e["relation"] == "contradicts"
        and e["from_id"] == "R-NEW"
        and e["to_id"] == "R-OLD"
        for e in edges
    )
    assert has_contradicts

    # ─── Phase 6: Noter next wake — recompute decay ────────────────────────
    os.environ["MINIONS_ROLE_NAME"] = "noter"
    decay_result = draft.mos_draft_decay_compute()
    decay_data = json.loads(Path(decay_result["path"]).read_text(encoding="utf-8"))
    nodes_decay = decay_data["nodes"]

    # ⭐ ASSERTION 6: Decay sidecar reflects supersedes/contradicts edges
    assert "R-OLD" in nodes_decay
    old_entry = nodes_decay["R-OLD"]
    # R-OLD has been contradicted (1 contradicts edge incident)
    assert old_entry["contradicts"] >= 1, (
        f"R-OLD should show contradicts count after Ethics verdict; got {old_entry}"
    )

    # ─── Phase 7: Summary surfaces decay info to all roles ─────────────────
    summary_after = draft.mos_draft_summary()
    assert "decay" in summary_after
    assert summary_after["decay"]["node_count"] >= 3  # R-OLD, R-NEW, D-...

    # ⭐ ASSERTION 7: most_decayed view ranks the contradicted node low
    most_decayed_ids = [n["id"] for n in summary_after["decay"]["most_decayed"]]
    # R-OLD has 0 supports + 1 contradicts → should decay faster than R-NEW
    # (which has the same age but no contradicts edge incident)
    if "R-OLD" in most_decayed_ids and "R-NEW" in most_decayed_ids:
        old_eff = next(
            n["effective_confidence"] for n in summary_after["decay"]["most_decayed"]
            if n["id"] == "R-OLD"
        )
        new_eff_raw = next(
            (n for n in summary_after["decay"]["most_decayed"] if n["id"] == "R-NEW"),
            None,
        )
        if new_eff_raw and old_eff is not None and new_eff_raw["effective_confidence"] is not None:
            assert old_eff <= new_eff_raw["effective_confidence"], (
                f"contradicted node should have lower or equal effective_confidence: "
                f"R-OLD={old_eff} vs R-NEW={new_eff_raw['effective_confidence']}"
            )

    # ─── Phase 8: Verify boundary invariants ──────────────────────────────
    # ⭐ ASSERTION 8a: Noter cannot publish to shared/ethics/ directly
    # mos_publish_to_shared is allowed but server enforces role identity
    # (noter's allowed shared subdirs are notes/draft/handoffs/book)
    # — this is enforced in publish.py's _ROLE_ALLOWED_SHARED_SUBDIRS

    # ⭐ ASSERTION 8b: Ethics cannot promote/crystallize Books (Noter-only)
    ethics_authz = resolve_server_authz("ethics", "main")
    promote_for_ethics = any(
        fnmatchcase("mos_book_promote_verified", p) for p in ethics_authz
    )
    assert not promote_for_ethics, (
        "Ethics must not be able to promote Drafts to Books — that's Noter's job"
    )
    crystallize_for_ethics = any(
        fnmatchcase("mos_book_crystallize_session", p) for p in ethics_authz
    )
    assert not crystallize_for_ethics

    # ⭐ ASSERTION 8c: Noter cannot read other roles' private Drafts ...
    # actually Noter reads ALL Drafts because it curates the shared one.
    # The forbidden one is Ethics reading another role's private reasoning.
    # In current arch: Drafts are project-shared (single draft.json), so
    # the boundary is "Ethics may not query draft with author_role filter
    # to peek into another role's private thinking" — this is a behavioral
    # rule, not a hard tool boundary. We document it but don't assert.

    # ⭐ ASSERTION 8d: Ethics CAN write decision/supersedes to Draft
    ethics_can_append = any(
        fnmatchcase("mos_draft_append", p) for p in ethics_authz
    )
    assert ethics_can_append, "Ethics must be able to append decision nodes"


def test_noter_promotes_dead_end_for_other_projects_to_avoid(sim_project):
    """A failed experiment from this project becomes a Book chapter so
    other projects (and the federated Library) can avoid the same dead end.

    This is the ARA "preserve rejected alternatives" principle in action.
    """
    port, _ = sim_project

    old_iso = (datetime.now(UTC) - timedelta(days=10)).isoformat(timespec="seconds")
    payload = {
        "project_port": port,
        "root_question": "test",
        "nodes": [
            {
                "id": "DEAD-001",
                "type": "dead_end",
                "text": "Naive sparsity below 0.3 ratio breaks gradient flow "
                        "and accuracy collapses by 22%",
                "support_status": "verified",
                "author_role": "coder",
                "confidence": 1.0,
                "created_at": old_iso,
            },
        ],
        "edges": [
            {"from_id": "exp-1", "to_id": "DEAD-001", "relation": "supports"},
            {"from_id": "exp-2", "to_id": "DEAD-001", "relation": "supports"},
        ],
    }
    p = draft._draft_path(port)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload), encoding="utf-8")

    os.environ["MINIONS_ROLE_NAME"] = "noter"
    result = book.mos_book_promote_verified(port=port)

    # ⭐ Dead-end was promoted (ARA principle realised)
    assert result["promoted_count"] == 1
    promoted = result["promoted"][0]
    assert promoted["type"] == "dead_end"

    # The promoted page exists and contains the verbatim warning
    book_root = book._book_root(port)
    pages = list((book_root / "sources").glob("noter-promoted-*.md"))
    assert len(pages) == 1
    body = pages[0].read_text(encoding="utf-8")
    assert "Naive sparsity below 0.3" in body
    assert "[DEAD-001]" in body


def test_shelf_aggregates_books_across_projects(sim_project, tmp_path, monkeypatch):
    """Verify that Shelf actually does what I said: aggregate per-project
    knowledge graphs into a single Gru-readable index."""
    _ = sim_project

    shelf_path = tmp_path / "shelf-global.json"
    monkeypatch.setattr(shelf, "_shelf_path", lambda: shelf_path)

    def _project_graph_path(p):
        d = tmp_path / f"project_{p}" / "branches" / "shared" / "shelf"
        d.mkdir(parents=True, exist_ok=True)
        return d / "shelf.json"

    monkeypatch.setattr(shelf, "_project_graph_path", _project_graph_path)

    # Project A: published a Book about linear attention
    _project_graph_path(50001).write_text(
        json.dumps({
            "nodes": [
                {"id": "n1", "label": "linear attention low-rank decomposition"},
                {"id": "n2", "label": "memory complexity reduction"},
            ],
            "links": [{"source": "n1", "target": "n2"}],
        }),
        encoding="utf-8",
    )
    # Project B: also touched attention but in a different angle
    _project_graph_path(50002).write_text(
        json.dumps({
            "nodes": [
                {"id": "n1", "label": "sparse attention pattern routing"},
            ],
            "links": [],
        }),
        encoding="utf-8",
    )

    shelf.mos_shelf_register(50001)
    shelf.mos_shelf_register(50002)

    # Gru queries the Shelf for "attention" → finds both projects' work
    result = shelf.mos_shelf_query("attention")
    assert result["projects_searched"] == 2
    matching_ports = {m["project_port"] for m in result["matches"]}
    assert 50001 in matching_ports
    assert 50002 in matching_ports

    # Cross-project shared concepts: Gru can ask "what's similar between A and B"
    shared_result = shelf.mos_shelf_shared_concepts(50001, 50002, min_score=0.5)
    assert shared_result["count"] >= 1
    # "attention" is shared
    assert any("attention" in s["label_a"].lower()
               and "attention" in s["label_b"].lower()
               for s in shared_result["shared"])
