"""Unit tests for Mission Profile system (v15-alpha)."""

from __future__ import annotations

import pytest

from minions.errors import ConfigError
from minions.profiles import (
    PROFILES_DIR,
    MissionProfile,
    get_default_profile,
    list_profiles,
    load_profile,
)


def test_profiles_dir_exists():
    """Profiles directory should exist."""
    assert PROFILES_DIR.exists()
    assert PROFILES_DIR.is_dir()


def test_list_profiles():
    """Should list available profile names."""
    profiles = list_profiles()
    assert isinstance(profiles, list)
    assert "scientific-paper" in profiles


def test_get_default_profile():
    """Default profile should be scientific-paper."""
    assert get_default_profile() == "scientific-paper"


def test_load_scientific_paper_profile():
    """Load and validate scientific-paper profile."""
    profile = load_profile("scientific-paper")
    assert isinstance(profile, MissionProfile)
    assert profile.name == "scientific-paper"
    assert profile.lightweight is False
    assert "gru" in profile.roles_active
    assert "expert" in profile.roles_active
    assert "ethics" in profile.roles_active
    assert "noter" not in profile.roles_active
    assert profile.phase_schema == "scientific_three_stage"
    assert profile.on_done == "none"

    # Check deliverable schema
    assert "publish_whitelist" in profile.deliverable_schema
    whitelist = profile.deliverable_schema["publish_whitelist"]
    assert isinstance(whitelist, dict)
    assert "gru" in whitelist
    assert "ethics" in whitelist
    assert "expert" in whitelist
    assert "noter" not in whitelist

    # Check evaluation
    assert "strategy" in profile.evaluation
    assert profile.evaluation["strategy"] == "scientific_peer_review"


def test_load_nonexistent_profile():
    """Loading a nonexistent profile should raise ConfigError."""
    with pytest.raises(ConfigError, match="not found"):
        load_profile("nonexistent-profile-xyz")


def test_gru_server_authz_includes_evaluator_tools():
    """mos_submit and mos_evaluate must be in Gru's server-side authz list.

    Regression test for v15-β: earlier draft added the tools to the CLI
    whitelist but forgot the server-side authz list, which would cause
    Gru's calls to be rejected at runtime by _require_tool_allowed.
    """
    from minions.config import resolve_server_authz

    auth = resolve_server_authz("gru", "main")
    assert "mos_submit" in auth, "mos_submit missing from Gru server-authz"
    assert "mos_evaluate" in auth, "mos_evaluate missing from Gru server-authz"


def test_other_roles_cannot_call_evaluator_tools():
    """Only Gru should be authorised for mos_submit / mos_evaluate.

    Other Roles must surface the deliverable to Gru via EACN message;
    this enforces the "Gru is the control plane" invariant.
    """
    from minions.config import resolve_server_authz

    for role in ["ethics", "expert", "noter"]:
        try:
            auth = resolve_server_authz(role, "main")
        except Exception:
            continue  # role not registered for main agent type
        assert "mos_submit" not in auth, f"mos_submit leaked to {role}"
        assert "mos_evaluate" not in auth, f"mos_evaluate leaked to {role}"
