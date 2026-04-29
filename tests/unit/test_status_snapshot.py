"""Unit tests for project_status_snapshot()."""

from __future__ import annotations

from unittest.mock import patch

from minions.lifecycle.health import project_status_snapshot


class TestProjectStatusSnapshot:
    def test_returns_required_keys(self) -> None:
        with patch("minions.lifecycle.health.backend_health", return_value=False):
            snap = project_status_snapshot(port=37596, project_status="active")
        required = {
            "port",
            "project_status",
            "backend_alive",
            "agents",
            "queue_depth",
            "pending_events",
            "gru_inbox_unread",
            "recent_health_events",
            "recent_failures",
        }
        assert required <= snap.keys()

    def test_dead_backend_returns_empty_agents(self) -> None:
        with patch("minions.lifecycle.health.backend_health", return_value=False):
            snap = project_status_snapshot(port=37596, project_status="active")
        assert snap["backend_alive"] is False
        assert snap["agents"] == []
        assert snap["queue_depth"] == 0

    def test_dormant_project_skips_probe(self) -> None:
        with patch("minions.lifecycle.health.backend_health") as mock_health:
            snap = project_status_snapshot(port=37596, project_status="dormant")
        mock_health.assert_not_called()
        assert snap["backend_alive"] is None

    def test_live_backend_includes_agents(self) -> None:
        fake_probe = {
            "health": True,
            "agents": [{"agent_id": "gru", "name": "Gru"}],
            "errors": [],
        }
        with (
            patch("minions.lifecycle.health.backend_health", return_value=True),
            patch("minions.lifecycle.eacn_client.probe_backend", return_value=fake_probe),
        ):
            snap = project_status_snapshot(port=37596, project_status="active")
        assert snap["backend_alive"] is True
        assert len(snap["agents"]) == 1
        assert snap["agents"][0]["agent_id"] == "gru"

    def test_closed_project_skips_probe(self) -> None:
        with patch("minions.lifecycle.health.backend_health") as mock_health:
            snap = project_status_snapshot(port=37596, project_status="closed")
        mock_health.assert_not_called()
        assert snap["backend_alive"] is None
        assert snap["agents"] == []

    def test_includes_recent_health_events(self, tmp_path, monkeypatch) -> None:
        from minions.lifecycle import health

        monkeypatch.setattr(
            health,
            "project_logs_dir",
            lambda port: tmp_path / f"project_{port}" / "logs",
        )
        health.append_health_event(
            port=37596,
            kind="backend_unhealthy",
            severity="warning",
            message="backend down",
        )
        with patch("minions.lifecycle.health.backend_health", return_value=False):
            snap = project_status_snapshot(port=37596, project_status="active")
        assert snap["recent_health_events"][0]["message"] == "backend down"
        assert "backend down" in snap["recent_failures"]

    def test_recovered_backend_does_not_surface_old_health_warning_as_current_failure(
        self, tmp_path, monkeypatch
    ) -> None:
        from minions.lifecycle import health

        monkeypatch.setattr(
            health,
            "project_logs_dir",
            lambda port: tmp_path / f"project_{port}" / "logs",
        )
        health.append_health_event(
            port=37596,
            kind="backend_unhealthy",
            severity="warning",
            message="[WARN] Backend on port 37596 is unhealthy.",
        )
        fake_probe = {
            "health": True,
            "agents": [],
            "errors": [],
            "queue_depth": 0,
            "pending_events": [],
        }
        with (
            patch("minions.lifecycle.health.backend_health", return_value=True),
            patch("minions.lifecycle.eacn_client.probe_backend", return_value=fake_probe),
        ):
            snap = project_status_snapshot(port=37596, project_status="active")
        assert snap["backend_alive"] is True
        assert snap["recent_health_events"][0]["message"] == (
            "[WARN] Backend on port 37596 is unhealthy."
        )
        assert snap["recent_failures"] == []
