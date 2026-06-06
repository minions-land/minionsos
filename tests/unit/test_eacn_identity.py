"""Tests for MinionsOS project-local EACN identity mapping."""

from __future__ import annotations

import json
from pathlib import Path

from minions.lifecycle import eacn_identity


def test_upsert_identity_writes_map_and_plugin_state(tmp_path: Path, monkeypatch) -> None:
    port = 40123
    pdir = tmp_path / f"project_{port}"
    pdir.mkdir()
    meta = pdir / "meta.json"
    meta.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(eacn_identity, "project_dir", lambda p: pdir)
    monkeypatch.setattr(eacn_identity, "project_meta_json", lambda p: meta)

    entry = eacn_identity.upsert_agent_identity(
        port,
        role_name="expert",
        agent_id="agent-expert",
        kind="role",
        server_id="srv-local",
        agent_token="tok",
        domains=["minionsos", "coding"],
        tier="general",
        description="Expert role",
        name="expert",
    )

    assert entry["agent_id"] == "agent-expert"
    assert eacn_identity.resolve_agent_id(port, "expert") == "agent-expert"
    assert eacn_identity.resolve_role_name(port, "agent-expert") == "expert"

    agent_map = json.loads((pdir / "eacn3_data" / "agent_map.json").read_text())
    assert agent_map["agents"]["expert"]["agent_id"] == "agent-expert"

    state_dir = pdir / "eacn3_data" / "plugin-agent-expert"
    server = json.loads((state_dir / "server.json").read_text())
    assert server["network_endpoint"] == f"http://127.0.0.1:{port}"
    agent = json.loads((state_dir / "agents" / "agent-expert.json").read_text())
    assert agent["agent"]["agent_id"] == "agent-expert"
    assert agent["agent"]["server_id"] == "srv-local"

    meta_payload = json.loads(meta.read_text())
    assert meta_payload["eacn_agent_map"]["expert"]["agent_id"] == "agent-expert"
