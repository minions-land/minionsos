"""Unit tests for adjudication defaults (issue #55)."""

from __future__ import annotations

from minions.tools.adjudicator import AdjudicateArgs, mos_adjudicate


def test_adjudicate_depth_none_skips():
    """depth=none should skip adjudication without touching EACN."""
    args = AdjudicateArgs(port=9999, depth="none")
    result = mos_adjudicate(args)
    assert result["status"] == "skipped"
    assert result["reason"] == "depth=none"


def test_adjudicate_missing_submission_returns_error(tmp_path, monkeypatch):
    """When no submission exists the tool should return status=error."""
    import minions.paths

    monkeypatch.setattr(minions.paths, "project_dir", lambda p: tmp_path)
    monkeypatch.setattr(minions.paths, "project_meta_json", lambda p: tmp_path / "meta.json")

    import json

    meta = {
        "port": 9999,
        "real_name": "test",
        "profile": "hle-answer",
        "profile_evaluation": {
            "strategy": "answer_grader",
            "adjudication": {"depth": "single"},
        },
    }
    (tmp_path / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    args = AdjudicateArgs(port=9999, depth="single")
    result = mos_adjudicate(args)
    assert result["status"] == "error"
    assert "answer.json" in result["reason"]
