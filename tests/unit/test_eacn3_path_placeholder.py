"""Tests for ${PROJECT_DIR} placeholder substitution at the EACN3 boundary.

Covers issue #47: outgoing EACN3 payloads strip absolute project paths
before persistence; incoming payloads rehydrate them with the live
project_dir. The substitution lives MinionsOS-side (eacn_client +
await_events + get_events), not in the EACN3 server.
"""

from __future__ import annotations

import os

from minions.lifecycle._path_placeholder import (
    PROJECT_DIR_PLACEHOLDER,
    decode_project_paths,
    encode_project_paths,
)

PDIR = "/Users/test/.minions/projects/project_37596"
SEP = os.sep


# ---------------------------------------------------------------------------
# Pure helper behaviour
# ---------------------------------------------------------------------------


def test_encode_decode_round_trip_nested():
    payload = {
        "file": f"{PDIR}{SEP}notes.md",
        "items": [
            {"path": f"{PDIR}{SEP}sub{SEP}dir{SEP}file.txt"},
            "unrelated",
            42,
        ],
        "meta": {"root": PDIR},
    }
    encoded = encode_project_paths(payload, PDIR)
    assert encoded["file"] == f"{PROJECT_DIR_PLACEHOLDER}{SEP}notes.md"
    assert (
        encoded["items"][0]["path"]
        == f"{PROJECT_DIR_PLACEHOLDER}{SEP}sub{SEP}dir{SEP}file.txt"
    )
    assert encoded["items"][1] == "unrelated"
    assert encoded["items"][2] == 42
    assert encoded["meta"]["root"] == PROJECT_DIR_PLACEHOLDER

    decoded = decode_project_paths(encoded, PDIR)
    assert decoded == payload


def test_encode_does_not_touch_embedded_substrings():
    """Only strings that ARE the path get rewritten; prose is left alone."""
    prose = f"see {PDIR}{SEP}notes.md for details"
    payload = {"msg": prose}
    encoded = encode_project_paths(payload, PDIR)
    assert encoded["msg"] == prose  # unchanged


def test_encode_handles_exact_equal_string():
    encoded = encode_project_paths({"d": PDIR}, PDIR)
    assert encoded["d"] == PROJECT_DIR_PLACEHOLDER


def test_encode_decode_noop_without_paths():
    payload = {"a": 1, "b": "hello world", "c": ["x", "y"]}
    assert encode_project_paths(payload, PDIR) == payload
    assert decode_project_paths(payload, PDIR) == payload


def test_encode_skips_similar_but_distinct_path():
    """A sibling project directory must NOT be rewritten."""
    sibling = f"/Users/test/.minions/projects/project_99999{SEP}x.txt"
    encoded = encode_project_paths({"p": sibling}, PDIR)
    assert encoded["p"] == sibling


# ---------------------------------------------------------------------------
# Boundary: outgoing via eacn_client._post_message_raw
# ---------------------------------------------------------------------------


def test_send_message_encodes_project_paths(monkeypatch, tmp_path):
    """_post_message_raw must rewrite project_dir-prefixed strings to the placeholder."""
    from minions.lifecycle import eacn_client

    # Force project_dir(port) → tmp_path so encode_project_paths has a real prefix.
    monkeypatch.setattr(eacn_client, "_project_dir", lambda port: tmp_path)

    captured = {}

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": 1}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["body"] = json
        return FakeResp()

    monkeypatch.setattr(eacn_client.httpx, "post", fake_post)

    abs_path = str(tmp_path / "notes.md")
    content = {"file": abs_path, "text": "hello"}

    eacn_client._post_message_raw(
        port=4999,
        to_agent_id="role-b",
        from_agent_id="role-a",
        content=content,
    )

    body = captured["body"]
    assert body["content"]["file"] == f"{PROJECT_DIR_PLACEHOLDER}{SEP}notes.md"
    import json as _json

    assert str(tmp_path) not in _json.dumps(body)


# ---------------------------------------------------------------------------
# Boundary: incoming via eacn_client.poll_events
# ---------------------------------------------------------------------------


def test_poll_events_decodes_project_paths(monkeypatch, tmp_path):
    """poll_events must rehydrate ${PROJECT_DIR} to the live project_dir."""
    from minions.lifecycle import eacn_client

    monkeypatch.setattr(eacn_client, "_project_dir", lambda port: tmp_path)

    server_response = {
        "events": [
            {
                "id": 1,
                "sender": "role-a",
                "recipient": "role-b",
                "payload": {"file": f"{PROJECT_DIR_PLACEHOLDER}{SEP}notes.md"},
            }
        ],
        "count": 1,
    }

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return server_response

    def fake_get(url, params=None, timeout=None):
        return FakeResp()

    monkeypatch.setattr(eacn_client.httpx, "get", fake_get)

    result = eacn_client.poll_events(port=4999, agent_id="role-b")
    expected_path = str(tmp_path / "notes.md")
    assert result["events"][0]["payload"]["file"] == expected_path
    assert PROJECT_DIR_PLACEHOLDER not in result["events"][0]["payload"]["file"]
