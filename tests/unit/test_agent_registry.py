"""Tests for project-local EACN AgentCard registration helpers."""

from __future__ import annotations

import json

import pytest

from minions.errors import BackendError
from minions.lifecycle import agent_registry, eacn_client


def test_project_eacn_server_id_reads_meta(tmp_path) -> None:
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"eacn3_server_id": "srv-local"}), encoding="utf-8")

    assert agent_registry.project_eacn_server_id(37596, meta_path=meta) == "srv-local"


def test_project_eacn_server_id_requires_server_id(tmp_path) -> None:
    meta = tmp_path / "meta.json"
    meta.write_text("{}", encoding="utf-8")

    with pytest.raises(BackendError):
        agent_registry.project_eacn_server_id(37596, meta_path=meta)


def test_register_project_role_agent_uses_role_name_as_agent_id(monkeypatch) -> None:
    calls = []

    def fake_register_agent(**kwargs):
        calls.append(kwargs)
        return "role-token", []

    monkeypatch.setattr(agent_registry.eacn_client, "register_agent", fake_register_agent)

    token, seeds = agent_registry.register_project_role_agent(
        37596,
        "noter",
        server_id="srv-local",
    )

    assert token == "role-token"
    assert seeds == []
    assert calls[0]["port"] == 37596
    assert calls[0]["agent_id"] == "noter"
    assert calls[0]["server_id"] == "srv-local"
    assert "project-local" in calls[0]["domains"]


def test_probe_backend_lists_minionsos_and_coordination_domains(monkeypatch) -> None:
    calls = []

    class FakeResp:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.text = json.dumps(payload)

        def json(self):
            return self._payload

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        if url.endswith("/health"):
            return FakeResp(200, {"status": "ok"})
        if url.endswith("/api/discovery/agents"):
            if params == {"domain": "minionsos"}:
                return FakeResp(200, [{"agent_id": "noter"}, {"agent_id": "coder"}])
            if params == {"domain": "coordination"}:
                return FakeResp(200, [{"agent_id": "gru"}, {"agent_id": "noter"}])
        if url.endswith("/api/tasks/open"):
            return FakeResp(200, [])
        return FakeResp(404, {})

    monkeypatch.setattr(eacn_client.httpx, "get", fake_get)

    snap = eacn_client.probe_backend(37596)

    assert {a["agent_id"] for a in snap["agents"]} == {"gru", "noter", "coder"}
    assert ("http://127.0.0.1:37596/api/discovery/agents", {"domain": "minionsos"}) in calls
    assert ("http://127.0.0.1:37596/api/discovery/agents", {"domain": "coordination"}) in calls
