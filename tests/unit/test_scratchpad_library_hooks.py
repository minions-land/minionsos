"""Unit tests for Phase 7 Scratchpad↔Library status hooks."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from minions.tools import scratchpad
from minions.tools import library


@pytest.fixture(autouse=True)
def _isolated_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Set up an isolated project directory for each test."""
    port = 9999
    shared = tmp_path / f"project_{port}" / "branches" / "shared"
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))
    monkeypatch.setenv("MINIONS_ROLE_NAME", "ethics")
    monkeypatch.setattr(
        scratchpad,
        "project_shared_subdir",
        lambda p, subdir: tmp_path / f"project_{p}" / "branches" / "shared" / subdir,
    )
    monkeypatch.setattr(
        scratchpad,
        "project_shared_scratchpad_json",
        lambda p: tmp_path / f"project_{p}" / "branches" / "shared" / "scratchpad" / "dag.json",
    )
    (shared / "scratchpad").mkdir(parents=True)
    return {"port": port, "shared": shared}


def _append_hypothesis(text: str = "Test hypothesis") -> None:
    scratchpad.mos_scratchpad_append(nodes=[{"type": "hypothesis", "text": text}])


def test_verified_status_triggers_wiki_status_hook(
    monkeypatch: pytest.MonkeyPatch,
    _isolated_project: dict[str, Any],
) -> None:
    calls: list[tuple[int, str, str, str]] = []

    def fake_emit(port: int, node_id: str, new_status: str, annotator: str) -> None:
        calls.append((port, node_id, new_status, annotator))

    monkeypatch.setattr(scratchpad, "_emit_library_status_event", fake_emit)
    _append_hypothesis()

    scratchpad.mos_scratchpad_annotate(node_id="H-001", support_status="verified")

    assert calls == [(_isolated_project["port"], "H-001", "verified", "ethics")]


def test_tentative_status_does_not_trigger_wiki_status_hook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_emit(port: int, node_id: str, new_status: str, annotator: str) -> None:
        raise AssertionError(f"unexpected wiki hook: {port} {node_id} {new_status} {annotator}")

    monkeypatch.setattr(scratchpad, "_emit_library_status_event", fail_emit)
    _append_hypothesis()

    scratchpad.mos_scratchpad_annotate(node_id="H-001", support_status="tentative")


def test_refuted_status_triggers_wiki_status_hook(
    monkeypatch: pytest.MonkeyPatch,
    _isolated_project: dict[str, Any],
) -> None:
    calls: list[tuple[int, str, str, str]] = []

    def fake_emit(port: int, node_id: str, new_status: str, annotator: str) -> None:
        calls.append((port, node_id, new_status, annotator))

    monkeypatch.setattr(scratchpad, "_emit_library_status_event", fake_emit)
    _append_hypothesis()

    scratchpad.mos_scratchpad_annotate(node_id="H-001", support_status="refuted")

    assert calls == [(_isolated_project["port"], "H-001", "refuted", "ethics")]


def test_wiki_status_hook_exception_does_not_propagate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_emit(port: int, node_id: str, new_status: str, annotator: str) -> None:
        del port, node_id, new_status, annotator
        raise RuntimeError("wiki unavailable")

    monkeypatch.setattr(scratchpad, "_emit_library_status_event", fail_emit)
    _append_hypothesis()

    result = scratchpad.mos_scratchpad_annotate(node_id="H-001", support_status="verified")

    assert result["changes"]["support_status"]["new"] == "verified"


def test_full_wiki_status_hook_calls_wiki_ingest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _isolated_project: dict[str, Any],
) -> None:
    calls: list[dict[str, object]] = []
    captured = tmp_path / "captured-status-event.md"

    def fake_mos_library_ingest(
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

    monkeypatch.setattr(library, "mos_library_ingest", fake_mos_library_ingest)
    _append_hypothesis("A long enough hypothesis for a wiki status update.")

    scratchpad.mos_scratchpad_annotate(node_id="H-001", support_status="verified")

    assert len(calls) == 1
    assert calls[0]["source_role"] == "noter"
    assert "verified" in str(calls[0]["source_slug"])
    assert calls[0]["port"] == _isolated_project["port"]
    assert calls[0]["title"] == "Status update: H-001 → verified"
    assert "**New status**: verified" in captured.read_text(encoding="utf-8")
