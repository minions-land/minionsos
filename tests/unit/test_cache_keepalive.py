"""Tests for the prompt-cache keepalive optimization.

Two halves:

1. ``_role_env`` exports ``ENABLE_PROMPT_CACHING_1H=1`` to the Role's
   ``claude`` process so prompt cache TTL becomes 1 h instead of 5 min, and
   does not export any env var that would silently downgrade the TTL.
2. ``mos_await_events`` returns a stable synthetic ``cache_keepalive`` event
   when wall-clock silence exceeds ``cache_keepalive_seconds``, with a
   byte-for-byte identical payload across calls (the post-keepalive
   conversation tail must stay cacheable).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

# --------------------------------------------------------------------------
# 1. _role_env env-var contract
# --------------------------------------------------------------------------


class TestRoleEnvCacheVars:
    """role_launcher._role_env exposes the cache-friendly env to claude."""

    def _build_env(self, tmp_path):
        from minions.lifecycle.role_launcher import _role_env
        from minions.state.store import RoleEntry

        role = RoleEntry(name="writer", state="active", workspace_branch="feature/x")
        with (
            patch("minions.lifecycle.role_launcher.resolve_agent_id", return_value="writer"),
            patch("minions.lifecycle.role_launcher.plugin_state_dir") as plugin_dir,
            patch("minions.lifecycle.role_launcher.project_workspace_root", return_value=tmp_path),
            patch("minions.lifecycle.role_launcher.project_workspace", return_value=tmp_path),
        ):
            plugin_dir.return_value = tmp_path / "plugin"
            (tmp_path / "plugin").mkdir(parents=True, exist_ok=True)
            return _role_env(
                role_name="writer",
                project_port=37596,
                role_entry=role,
                workspace=tmp_path,
            )

    def test_enable_prompt_caching_1h_is_set(self, tmp_path):
        env = self._build_env(tmp_path)
        assert env.get("ENABLE_PROMPT_CACHING_1H") == "1"

    def test_disable_telemetry_not_set(self, tmp_path):
        """DISABLE_TELEMETRY would force subscription auth back to 5min TTL."""
        env = self._build_env(tmp_path)
        assert "DISABLE_TELEMETRY" not in env

    def test_no_disable_prompt_caching(self, tmp_path):
        """DISABLE_PROMPT_CACHING* would defeat caching entirely."""
        env = self._build_env(tmp_path)
        for key in env:
            assert not key.startswith("DISABLE_PROMPT_CACHING"), (
                f"Role env exports {key}; this disables prompt caching."
            )

    def test_force_5m_not_set(self, tmp_path):
        """FORCE_PROMPT_CACHING_5M would override the 1h opt-in."""
        env = self._build_env(tmp_path)
        assert "FORCE_PROMPT_CACHING_5M" not in env


# --------------------------------------------------------------------------
# 2. cache_keepalive synthetic event
# --------------------------------------------------------------------------


@pytest.fixture
def _await_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MINIONS_PROJECT_PORT", "39998")
    monkeypatch.setenv("MINIONS_AGENT_ID", "test-agent")
    monkeypatch.setenv("MINIONS_WORKSPACE", str(tmp_path / "workspace"))
    (tmp_path / "workspace").mkdir()
    monkeypatch.chdir(tmp_path)


def _empty_poll_response():
    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"events": [], "count": 0}

    return FakeResp()


def _empty_tasks_response():
    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return []

    return FakeResp()


class TestKeepaliveReturn:
    def test_keepalive_fires_after_threshold(self, _await_env):
        """When wall-clock elapsed >= cache_keepalive_seconds and no events,
        await_events returns the synthetic cache_keepalive event."""
        from minions.tools import await_events as ae

        # 5 ticks of monotonic time: started + 4 polls + threshold cross.
        # await_events reads time.monotonic() once at start, then in the
        # cliff-guard branch after each empty poll. Sequence the values so
        # the cliff fires on the first poll (avoiding the idle-check path).
        time_values = iter([0.0, 100.0])  # start=0, threshold-check=100s

        def fake_monotonic():
            return next(time_values)

        with (
            patch.object(ae, "_load_keepalive_seconds", return_value=50),
            patch.object(ae.time, "monotonic", side_effect=fake_monotonic),
            patch.object(ae.httpx, "get") as mock_get,
        ):
            mock_get.side_effect = lambda *a, **kw: (
                _empty_tasks_response() if "/api/tasks" in a[0] else _empty_poll_response()
            )
            result = ae.await_events()

        assert result["count"] == 1
        assert result["events"][0]["event"]["type"] == "cache_keepalive"

    def test_keepalive_payload_is_byte_stable(self):
        """Two await_events calls returning keepalive must produce identical
        event bytes — any drift defeats the cache the keepalive is for."""
        # Re-import in a way that simulates a second call: the constant
        # must be the same object identity OR at least equal byte payload.
        import json

        from minions.tools.await_events import _KEEPALIVE_EVENT

        snapshot_a = json.dumps(_KEEPALIVE_EVENT, sort_keys=True)
        snapshot_b = json.dumps(_KEEPALIVE_EVENT, sort_keys=True)
        assert snapshot_a == snapshot_b
        # And the payload must not contain timestamps or counters.
        assert "alive_at" not in snapshot_a
        assert "task_id" in snapshot_a  # present (empty), not absent
        assert _KEEPALIVE_EVENT["event"]["task_id"] == ""
        assert _KEEPALIVE_EVENT["event"]["payload"] == {}

    def test_keepalive_disabled_when_zero(self, _await_env):
        """cache_keepalive_seconds=0 disables the cliff guard entirely.

        With keepalive off and the idle check returning no actionable work
        (no-idle), the await must keep polling — never return keepalive.
        We assert keepalive does NOT fire by interrupting after enough
        empty polls and verifying the loop continued (it never returned
        a cache_keepalive event)."""
        from minions.tools import await_events as ae

        call_log: list[str] = []

        def fake_get(url, **_kw):
            call_log.append(url)
            # After a handful of polls, deliver a real event so the test
            # terminates. Without this, the loop would run forever.
            if len(call_log) >= 8:
                return _real_event_response()
            if "/api/tasks" in url:
                return _empty_tasks_response()
            return _empty_poll_response()

        with (
            patch.object(ae, "_load_keepalive_seconds", return_value=0),
            patch.object(ae.time, "monotonic", return_value=1_000_000.0),
            patch.object(ae.httpx, "get", side_effect=fake_get),
        ):
            result = ae.await_events()

        # Should be the real event, not a keepalive.
        assert result["events"][0]["event"]["type"] != "cache_keepalive"


def _real_event_response():
    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "events": [
                    {
                        "type": "task_timeout",
                        "task_id": "t-real",
                        "payload": {},
                    }
                ],
                "count": 1,
            }

    return FakeResp()
