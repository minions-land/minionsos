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
    monkeypatch.setattr(agent_registry, "upsert_agent_identity", lambda *args, **kwargs: {})

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


def test_post_message_rejects_unknown_target_agent(monkeypatch) -> None:
    posts = []

    class FakeResp:
        status_code = 404
        text = '{"detail": "not found"}'

        def json(self):
            return {"detail": "not found"}

    def fake_get(url, timeout=None):
        assert url.endswith("/api/discovery/agents/codre")
        return FakeResp()

    def fake_post(**kwargs):
        posts.append(kwargs)

    monkeypatch.setattr(eacn_client.httpx, "get", fake_get)
    monkeypatch.setattr(eacn_client.httpx, "post", fake_post)

    with pytest.raises(BackendError, match="target agent 'codre' is not registered"):
        eacn_client.send_message(
            port=37596,
            to_agent_id="codre",
            from_agent_id="gru",
            content="hello",
        )

    assert posts == []


def test_post_message_does_not_mirror_to_noter(monkeypatch) -> None:
    """Direct messages go straight to the recipient — no audit fan-out.

    The old eacn_client used to mirror every message to Noter as a
    "network_audit_message". That implicit fan-out has been removed; Noter
    observes its own EACN queue like any other role.
    """
    gets: list[str] = []
    posts: list[dict] = []

    class FakeResp:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.text = json.dumps(payload)

        def json(self):
            return self._payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(self.text)

    def fake_get(url, timeout=None):
        gets.append(url)
        if url.endswith("/api/discovery/agents/coder"):
            return FakeResp(200, {"agent_id": "coder"})
        if url.endswith("/api/discovery/agents/noter"):
            return FakeResp(200, {"agent_id": "noter"})
        return FakeResp(404, {})

    def fake_post(url, json=None, timeout=None):
        posts.append({"url": url, "json": json})
        return FakeResp(200, {"ok": True, "delivered": 1})

    monkeypatch.setattr(eacn_client.httpx, "get", fake_get)
    monkeypatch.setattr(eacn_client.httpx, "post", fake_post)

    result = eacn_client.send_message(
        port=37596,
        to_agent_id="coder",
        from_agent_id="writer",
        content={"type": "handoff", "text": "draft ready"},
    )

    assert result == {"ok": True, "delivered": 1}
    assert len(posts) == 1
    assert posts[0]["json"]["to"]["agent_id"] == "coder"
