"""Unit tests for paper-search helper safety behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from minions.tools import paper_search


def test_relative_output_path_stays_under_current_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MINIONS_PROJECT_PORT", raising=False)
    monkeypatch.chdir(tmp_path)

    path = paper_search._relative_output_path("paper/references", "x.txt")

    assert path == tmp_path / "paper" / "references" / "x.txt"
    assert path.parent.is_dir()


def test_relative_output_path_rejects_absolute(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="relative"):
        paper_search._relative_output_path(str(tmp_path), "x.txt")


def test_relative_output_path_rejects_parent_traversal() -> None:
    with pytest.raises(ValueError, match="must not contain"):
        paper_search._relative_output_path("../outside", "x.txt")


def test_limit_clamps_search_result_count() -> None:
    assert paper_search._limit(0) == 1
    assert paper_search._limit(10) == 10
    assert paper_search._limit(500) == paper_search.MAX_RESULTS
