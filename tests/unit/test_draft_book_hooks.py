"""Unit tests for Phase 7 Draft↔Book status hooks."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from minions.tools import book, draft


@pytest.fixture(autouse=True)
def _isolated_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Set up an isolated project directory for each test."""
    port = 9999
    shared = tmp_path / f"project_{port}" / "branches" / "shared"
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))
    monkeypatch.setenv("MINIONS_ROLE_NAME", "ethics")
    monkeypatch.setattr(
        draft,
        "project_shared_subdir",
        lambda p, subdir: tmp_path / f"project_{p}" / "branches" / "shared" / subdir,
    )
    monkeypatch.setattr(
        draft,
        "project_shared_draft_json",
        lambda p: tmp_path / f"project_{p}" / "branches" / "shared" / "draft" / "dag.json",
    )
    (shared / "draft").mkdir(parents=True)
    return {"port": port, "shared": shared}


def _append_hypothesis(text: str = "Test hypothesis") -> None:
    draft.mos_draft_append(nodes=[{"type": "hypothesis", "text": text}])


def test_verified_status_triggers_wiki_status_hook(
    monkeypatch: pytest.MonkeyPatch,
    _isolated_project: dict[str, Any],
) -> None:
    calls: list[tuple[int, str, str, str]] = []

    def fake_emit(port: int, node_id: str, new_status: str, annotator: str) -> None:
        calls.append((port, node_id, new_status, annotator))

    monkeypatch.setattr(draft, "_emit_book_status_event", fake_emit)
    _append_hypothesis()

    draft.mos_draft_annotate(node_id="H-001", support_status="verified")

    assert calls == [(_isolated_project["port"], "H-001", "verified", "ethics")]


def test_tentative_status_does_not_trigger_book_status_hook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_emit(port: int, node_id: str, new_status: str, annotator: str) -> None:
        raise AssertionError(f"unexpected book hook: {port} {node_id} {new_status} {annotator}")

    monkeypatch.setattr(draft, "_emit_book_status_event", fail_emit)
    _append_hypothesis()

    draft.mos_draft_annotate(node_id="H-001", support_status="tentative")


def test_refuted_status_triggers_wiki_status_hook(
    monkeypatch: pytest.MonkeyPatch,
    _isolated_project: dict[str, Any],
) -> None:
    calls: list[tuple[int, str, str, str]] = []

    def fake_emit(port: int, node_id: str, new_status: str, annotator: str) -> None:
        calls.append((port, node_id, new_status, annotator))

    monkeypatch.setattr(draft, "_emit_book_status_event", fake_emit)
    _append_hypothesis()

    draft.mos_draft_annotate(node_id="H-001", support_status="refuted")

    assert calls == [(_isolated_project["port"], "H-001", "refuted", "ethics")]


def test_wiki_status_hook_exception_does_not_propagate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_emit(port: int, node_id: str, new_status: str, annotator: str) -> None:
        del port, node_id, new_status, annotator
        raise RuntimeError("book unavailable")

    monkeypatch.setattr(draft, "_emit_book_status_event", fail_emit)
    _append_hypothesis()

    result = draft.mos_draft_annotate(node_id="H-001", support_status="verified")

    assert result["changes"]["support_status"]["new"] == "verified"


def test_full_wiki_status_hook_calls_wiki_ingest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _isolated_project: dict[str, Any],
) -> None:
    calls: list[dict[str, object]] = []
    captured = tmp_path / "captured-status-event.md"

    def fake_mos_book_ingest(
        src_path: str,
        source_role: str,
        source_slug: str,
        title: str | None = None,
        summary: str | None = None,
        *,
        port: int | None = None,
    ) -> dict[str, object]:
        del summary
        src = Path(src_path)
        assert src.exists()
        shutil.copy2(src, captured)
        calls.append(
            {
                "src_path": src_path,
                "source_role": source_role,
                "source_slug": source_slug,
                "title": title,
                "port": port,
            }
        )
        return {"slug": source_slug}

    monkeypatch.setattr(book, "mos_book_ingest", fake_mos_book_ingest)
    _append_hypothesis("A long enough hypothesis for a book status update.")

    draft.mos_draft_annotate(node_id="H-001", support_status="verified")

    assert len(calls) == 1
    assert calls[0]["source_role"] == "ethics"
    assert "verified" in str(calls[0]["source_slug"])
    assert calls[0]["port"] == _isolated_project["port"]
    assert calls[0]["title"] == "Status update: H-001 → verified"
    assert "**New status**: verified" in captured.read_text(encoding="utf-8")
