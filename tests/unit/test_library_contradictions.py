"""Unit tests for Phase 5 library contradiction detection."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from minions.paths import (
    project_shared_branch_name,
    project_shared_scratchpad_json,
    project_shared_workspace,
    project_state_dir,
)
from minions.tools import library

POSITIVE_SENTENCE = (
    "The transformer cache can improve latency because repeated retrieval keeps "
    "attention state stable during project wakeups."
)
NEGATIVE_SENTENCE = (
    "The transformer cache does not improve latency because repeated retrieval "
    "keeps attention state stable during project wakeups."
)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    port = 42345
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path))
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))
    shared = project_shared_workspace(port)
    (shared / "coder").mkdir(parents=True)
    (shared / "expert").mkdir(parents=True)
    (shared / "library" / "sources").mkdir(parents=True)
    project_state_dir(port).mkdir(parents=True)
    return {"port": port, "shared": shared}


def _mock_publish(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    publish_results: list[dict[str, object]] = []

    def fake_publish_to_shared(
        *,
        role: str,
        src_path: str,
        dst_subpath: str,
        commit_message: str,
        port: int | None = None,
        store: object | None = None,
    ) -> dict[str, object]:
        del store
        assert role == "noter"
        assert commit_message.startswith("noter: ingest ")
        resolved_port = port or library._env_port()
        src = Path(src_path)
        dst = project_shared_workspace(resolved_port) / dst_subpath
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        result: dict[str, object] = {
            "port": resolved_port,
            "role": role,
            "dst_path": dst_subpath,
            "commit_sha": f"fake-{len(publish_results) + 1}",
            "pushed": False,
            "push_branch": None,
            "branch": project_shared_branch_name(resolved_port),
        }
        publish_results.append(result)
        return result

    monkeypatch.setattr(library, "mos_publish_to_shared", fake_publish_to_shared)
    return publish_results


def _write_existing_source(shared: Path, slug: str, body: str, source_role: str = "expert") -> Path:
    page = shared / "library" / "sources" / f"{slug}.md"
    page.write_text(
        "\n".join(
            [
                "---",
                "type: source",
                f'slug: "{slug}"',
                f'source_role: "{source_role}"',
                "page_kind: source",
                "---",
                "",
                body,
                "",
            ]
        ),
        encoding="utf-8",
    )
    return page


def _write_artifact(shared: Path, role: str, name: str, body: str) -> Path:
    artifact = shared / role / name
    artifact.write_text(body + "\n", encoding="utf-8")
    return artifact


def test_no_existing_pages_creates_no_contradiction_page(
    project: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_publish(monkeypatch)
    artifact = _write_artifact(project["shared"], "coder", "cache.md", NEGATIVE_SENTENCE)

    result = library.mos_library_ingest(str(artifact), "coder", "cache", port=project["port"])

    assert result["contradiction_count"] == 0
    assert result["contradiction_path"] is None
    assert not (project["shared"] / "library" / "contradictions").exists()


def test_opposed_claims_create_contradiction_page_with_frontmatter(
    project: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_publish(monkeypatch)
    _write_existing_source(project["shared"], "expert-cache", POSITIVE_SENTENCE)
    artifact = _write_artifact(project["shared"], "coder", "cache.md", NEGATIVE_SENTENCE)

    result = library.mos_library_ingest(str(artifact), "coder", "cache", port=project["port"])

    contradiction = project["shared"] / "library" / "contradictions" / "contradiction-coder-cache.md"
    assert contradiction.exists()
    text = contradiction.read_text(encoding="utf-8")
    assert result["contradiction_count"] == 1
    assert result["contradiction_path"] == "library/contradictions/contradiction-coder-cache.md"
    assert "type: contradiction" in text
    assert 'slug: "contradiction-coder-cache"' in text
    assert 'new_source: "coder-cache"' in text
    assert 'new_source_role: "coder"' in text
    assert "opposing_count: 1" in text
    assert 'date_detected: "' in text
    assert "page_kind: contradiction" in text
    assert "status: unresolved" in text
    assert "> [!contradiction]" in text
    assert "Opposing page: `library/sources/expert-cache.md`" in text
    assert "`improve`" in text


def test_non_opposed_pages_create_no_contradiction(
    project: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_publish(monkeypatch)
    _write_existing_source(project["shared"], "expert-cache", POSITIVE_SENTENCE)
    artifact = _write_artifact(project["shared"], "coder", "cache.md", POSITIVE_SENTENCE)

    result = library.mos_library_ingest(str(artifact), "coder", "cache", port=project["port"])

    assert result["contradiction_count"] == 0
    assert not (project["shared"] / "library" / "contradictions").exists()


def test_short_sentences_are_ignored(
    project: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_publish(monkeypatch)
    _write_existing_source(project["shared"], "expert-cache", "Cache improves.")
    artifact = _write_artifact(project["shared"], "coder", "cache.md", "Cache does not improve.")

    result = library.mos_library_ingest(str(artifact), "coder", "cache", port=project["port"])

    assert result["contradiction_count"] == 0
    assert not (project["shared"] / "library" / "contradictions").exists()


def test_reingest_is_idempotent_for_contradiction_index_entries(
    project: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_publish(monkeypatch)
    _write_existing_source(project["shared"], "expert-cache", POSITIVE_SENTENCE)
    artifact = _write_artifact(project["shared"], "coder", "cache.md", NEGATIVE_SENTENCE)

    library.mos_library_ingest(str(artifact), "coder", "cache", port=project["port"])
    result = library.mos_library_ingest(str(artifact), "coder", "cache", port=project["port"])

    index = (project["shared"] / "library" / "index.md").read_text(encoding="utf-8")
    assert result["contradiction_count"] == 1
    assert index.count("slug: coder-cache") == 1
    assert index.count("slug: contradiction-coder-cache") == 1


def test_dag_edge_emitted_when_both_endpoints_exist(
    project: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_publish(monkeypatch)
    _write_existing_source(project["shared"], "expert-cache", POSITIVE_SENTENCE)
    artifact = _write_artifact(project["shared"], "coder", "cache.md", NEGATIVE_SENTENCE)
    dag_path = project_shared_scratchpad_json(project["port"])
    dag_path.parent.mkdir(parents=True, exist_ok=True)
    dag_path.write_text(
        json.dumps(
            {
                "project_port": project["port"],
                "root_question": "",
                "nodes": [
                    {"id": "H-001", "type": "hypothesis", "text": POSITIVE_SENTENCE},
                    {"id": "H-002", "type": "hypothesis", "text": NEGATIVE_SENTENCE},
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )

    result = library.mos_library_ingest(str(artifact), "coder", "cache", port=project["port"])

    dag = json.loads(dag_path.read_text(encoding="utf-8"))
    assert result["dag_edges_created"] == 1
    assert dag["edges"] == [
        {
            "from_id": "H-002",
            "to_id": "H-001",
            "relation": "contradicts",
            "strength": 0.5,
            "created_at": dag["edges"][0]["created_at"],
            "author_role": "noter",
        }
    ]


def test_dag_edge_skipped_gracefully_when_no_match(
    project: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_publish(monkeypatch)
    _write_existing_source(project["shared"], "expert-cache", POSITIVE_SENTENCE)
    artifact = _write_artifact(project["shared"], "coder", "cache.md", NEGATIVE_SENTENCE)
    dag_path = project_shared_scratchpad_json(project["port"])
    dag_path.parent.mkdir(parents=True, exist_ok=True)
    dag_path.write_text(
        json.dumps(
            {
                "project_port": project["port"],
                "root_question": "",
                "nodes": [{"id": "H-001", "type": "hypothesis", "text": "unrelated"}],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )

    result = library.mos_library_ingest(str(artifact), "coder", "cache", port=project["port"])

    dag = json.loads(dag_path.read_text(encoding="utf-8"))
    assert result["dag_edges_created"] == 0
    assert dag["edges"] == []


def test_contradiction_index_entry_uses_contradictions_path(project: dict[str, Any]) -> None:
    stage = library._index_append(
        project["port"],
        "contradiction-coder-cache",
        "Contradiction: coder-cache",
        "contradiction",
    )

    text = stage.read_text(encoding="utf-8")
    assert "slug: contradiction-coder-cache" in text
    assert "page_kind: contradiction" in text
    assert "library_path: library/contradictions/contradiction-coder-cache.md" in text


def test_ethics_system_mentions_library_contradiction_workflow() -> None:
    text = Path("minions/roles/ethics/SYSTEM.md").read_text(encoding="utf-8")

    assert "## Contradiction surface (Library Layer 2 — phase 5+)" in text
    assert "primary hallucination audit feed" in text
    assert "resolved-in-favor-of-new" in text
    assert "resolved-in-favor-of-existing" in text
    assert "both-correct-different-scope" in text
    assert "needs-experiment" in text
    assert "out-of-scope" in text
    assert "branches/shared/ethics/contradiction-<slug>-verdict.md" in text
    assert "higher-precedence" in text
    assert "message-stream grepping" in text
    assert "Do not modify `library/contradictions/*` or `library/index.md`" in text
