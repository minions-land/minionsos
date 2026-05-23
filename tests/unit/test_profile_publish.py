"""Unit tests for profile-aware publish whitelist (v15-gamma)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minions.errors import ProjectError


def test_default_role_allowed_subdirs():
    """Default whitelist should be returned when no profile is set."""
    from minions.tools.publish import _allowed_subdirs_for_role

    # Use a port with no meta.json - returns the default
    allowed = _allowed_subdirs_for_role("ethics", port=99000)
    assert allowed is not None
    assert "ethics" in allowed
    assert "handoffs" in allowed


def test_default_gru_wildcard():
    """Gru should always have wildcard access."""
    from minions.tools.publish import _allowed_subdirs_for_role

    allowed = _allowed_subdirs_for_role("gru", port=99000)
    assert allowed == {"*"}


def test_unknown_role_returns_none():
    """Unknown role should return None."""
    from minions.tools.publish import _allowed_subdirs_for_role

    allowed = _allowed_subdirs_for_role("nonexistent-role", port=99000)
    assert allowed is None


def test_profile_overrides_default(tmp_path, monkeypatch):
    """HLE profile should override default whitelist."""
    port = 8888
    project_root = tmp_path / f"project_{port}"
    project_root.mkdir()

    meta = {
        "port": port,
        "profile": "hle-answer",
        "profile_deliverable_schema": {
            "publish_whitelist": {
                "gru": ["*"],
                "expert": ["handoffs", "submissions"],
                "coder": ["exp", "handoffs", "submissions"],
            },
        },
    }
    meta_path = project_root / "meta.json"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    def mock_project_meta_json(p: int) -> Path:
        return meta_path

    # Patch in the publish module's import
    import minions.paths

    monkeypatch.setattr(minions.paths, "project_meta_json", mock_project_meta_json)

    from minions.tools.publish import _allowed_subdirs_for_role

    # Coder under HLE profile should have submissions allowed
    coder_allowed = _allowed_subdirs_for_role("coder", port=port)
    assert coder_allowed is not None
    assert "submissions" in coder_allowed
    assert "exp" in coder_allowed

    # Expert under HLE profile should have submissions allowed
    expert_allowed = _allowed_subdirs_for_role("expert", port=port)
    assert expert_allowed is not None
    assert "submissions" in expert_allowed


def test_validate_dst_default_role():
    """Validate paths with default role policy."""
    from minions.tools.publish import _validate_dst

    # ethics may publish to handoffs
    result = _validate_dst("ethics", "handoffs/note.md", port=99001)
    assert str(result) == "handoffs/note.md"

    # ethics may NOT publish to submissions (under default profile)
    with pytest.raises(ProjectError, match="may not publish"):
        _validate_dst("ethics", "submissions/answer.json", port=99001)


def test_validate_dst_reserved_root():
    """Reviews/ subdir is reserved."""
    from minions.tools.publish import _validate_dst

    with pytest.raises(ProjectError, match="reserved for mos_review_run"):
        _validate_dst("gru", "reviews/round-1/note.md", port=99001)


def test_validate_dst_path_traversal():
    """Reject .. path traversal."""
    from minions.tools.publish import _validate_dst

    with pytest.raises(ProjectError, match="may not escape"):
        _validate_dst("gru", "handoffs/../etc/passwd", port=99001)


def test_validate_dst_absolute_path():
    """Reject absolute paths."""
    from minions.tools.publish import _validate_dst

    with pytest.raises(ProjectError, match="must be a relative path"):
        _validate_dst("gru", "/etc/passwd", port=99001)


def test_validate_dst_empty():
    """Reject empty subpath."""
    from minions.tools.publish import _validate_dst

    with pytest.raises(ProjectError):
        _validate_dst("gru", "", port=99001)


def test_expert_role_normalisation():
    """expert-foo should collapse to expert."""
    from minions.tools.publish import _allowed_subdirs_for_role

    allowed = _allowed_subdirs_for_role("expert-physics", port=99000)
    assert allowed is not None
    # Expert default policy
    assert "handoffs" in allowed
