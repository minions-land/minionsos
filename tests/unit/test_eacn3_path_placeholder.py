"""Tests for project-path placeholder substitution at the EACN3 boundary.

Issue #47: ``offline_messages.payload`` rows must not embed absolute project
paths or the project becomes non-portable. Outgoing payloads have the
``project_dir(port)`` prefix replaced with ``${PROJECT_DIR}`` before EACN3
persists them; incoming payloads have the placeholder hydrated back to the
live ``project_dir(port)`` at the MinionsOS reader boundary.

The EACN3 server stays project-agnostic — it does not know the
port-to-directory mapping; that knowledge lives on the MinionsOS side
(``minions.paths.project_dir``).
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from minions.lifecycle._path_placeholder import (
    PROJECT_DIR_PLACEHOLDER,
    decode_project_paths,
    encode_project_paths,
)

PROJECT_DIR = "/tmp/project_37596"


# ---------------------------------------------------------------------------
# Pure helper tests (no I/O)
# ---------------------------------------------------------------------------


def test_encode_decode_round_trip_nested_payload():
    payload = {
        "file": f"{PROJECT_DIR}/notes.md",
        "meta": {
            "paths": [f"{PROJECT_DIR}/a.txt", f"{PROJECT_DIR}/sub/b.txt"],
            "unrelated": "hello world",
        },
        "count": 3,
    }
    encoded = encode_project_paths(payload, PROJECT_DIR)
    assert encoded["file"] == f"{PROJECT_DIR_PLACEHOLDER}{os.sep}notes.md"
    assert encoded["meta"]["paths"][0] == f"{PROJECT_DIR_PLACEHOLDER}{os.sep}a.txt"
    assert encoded["meta"]["paths"][1] == f"{PROJECT_DIR_PLACEHOLDER}{os.sep}sub{os.sep}b.txt"
    assert encoded["meta"]["unrelated"] == "hello world"
    assert encoded["count"] == 3
    decoded = decode_project_paths(encoded, PROJECT_DIR)
    assert decoded == payload


def test_encode_does_not_touch_substring_inside_arbitrary_text():
    text = f"see {PROJECT_DIR}/notes.md for details"
    payload = {"msg": text}
    encoded = encode_project_paths(payload, PROJECT_DIR)
    # Project dir appears as a substring, not a prefix, of the value -> untouched.
    assert encoded["msg"] == text


def test_encode_handles_exact_equal():
    payload = {"root": PROJECT_DIR}
    encoded = encode_project_paths(payload, PROJECT_DIR)
    assert encoded["root"] == PROJECT_DIR_PLACEHOLDER
    decoded = decode_project_paths(encoded, PROJECT_DIR)
    assert decoded["root"] == PROJECT_DIR


def test_encode_decode_noop_without_project_paths():
    payload = {"a": 1, "b": ["x", "y"], "c": {"d": "unrelated/path"}}
    assert encode_project_paths(payload, PROJECT_DIR) == payload
    assert decode_project_paths(payload, PROJECT_DIR) == payload


def test_encode_does_not_mutate_input():
    payload = {"file": f"{PROJECT_DIR}/notes.md", "list": [f"{PROJECT_DIR}/a"]}
    snapshot = {"file": payload["file"], "list": list(payload["list"])}
    encode_project_paths(payload, PROJECT_DIR)
    assert payload == snapshot


# ---------------------------------------------------------------------------
# Outgoing seam: eacn_client._post_message_raw must rewrite project paths
# before they leave for the EACN3 server (offline_messages portability).
# ---------------------------------------------------------------------------


class _FakeResp:
    status_code = 200

    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


def test_post_message_raw_encodes_project_paths_in_outgoing_body():
    from minions.lifecycle import eacn_client
    from minions.paths import project_dir

    port = 37596
    proj = str(project_dir(port))
    abs_path = f"{proj}/notes.md"

    captured = {}

    def fake_post(url, json, timeout):  # noqa: A002 - matches httpx kw
        captured["url"] = url
        captured["json"] = json
        return _FakeResp({"ok": True})

    with patch.object(eacn_client.httpx, "post", side_effect=fake_post):
        eacn_client._post_message_raw(
            port=port,
            to_agent_id="bob",
            from_agent_id="alice",
            content={"file": abs_path, "text": "hi"},
        )

    sent_content = captured["json"]["content"]
    assert sent_content["text"] == "hi"
    assert sent_content["file"] == f"{PROJECT_DIR_PLACEHOLDER}{os.sep}notes.md"
    # Crucially: the absolute project path must not leak into the persisted body.
    assert proj not in sent_content["file"]


# ---------------------------------------------------------------------------
# Incoming seam 1: eacn_client.poll_events must hydrate placeholders.
# ---------------------------------------------------------------------------


def test_poll_events_hydrates_placeholder_on_read():
    from minions.lifecycle import eacn_client
    from minions.paths import project_dir

    port = 37596
    proj = str(project_dir(port))
    placeholder_path = f"{PROJECT_DIR_PLACEHOLDER}{os.sep}notes.md"
    server_response = {
        "events": [
            {
                "type": "direct_message",
                "task_id": "t-1",
                "payload": {"file": placeholder_path, "text": "hi"},
            }
        ],
        "count": 1,
    }

    def fake_get(url, params, timeout):  # noqa: A002
        return _FakeResp(server_response)

    with patch.object(eacn_client.httpx, "get", side_effect=fake_get):
        out = eacn_client.poll_events(port, "alice", timeout_secs=0)

    evt = out["events"][0]
    assert evt["payload"]["file"] == f"{proj}{os.sep}notes.md"
    assert evt["payload"]["text"] == "hi"
    assert PROJECT_DIR_PLACEHOLDER not in evt["payload"]["file"]


# ---------------------------------------------------------------------------
# Incoming seam 2: minions.tools.await_events._poll_once is the role-wake
# path; it does its own GET and must hydrate placeholders before they reach
# the role's annotation logic.
# ---------------------------------------------------------------------------


@pytest.fixture
def _await_events_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MINIONS_PROJECT_PORT", "37596")
    monkeypatch.setenv("MINIONS_AGENT_ID", "alice")
    monkeypatch.setenv("MINIONS_WORKSPACE", str(tmp_path / "ws"))
    (tmp_path / "ws").mkdir()
    monkeypatch.chdir(tmp_path)


def test_mos_await_events_hydrates_placeholder_on_read(_await_events_env):
    from minions.paths import project_dir
    from minions.tools.await_events import await_events

    port = 37596
    proj = str(project_dir(port))
    placeholder_path = f"{PROJECT_DIR_PLACEHOLDER}{os.sep}notes.md"
    server_response = {
        "events": [
            {
                "type": "direct_message",
                "task_id": "t-1",
                "payload": {
                    "from": "gru",
                    "content": "see file",
                    "file": placeholder_path,
                },
            }
        ],
        "count": 1,
    }

    def fake_get(url, params=None, timeout=None):  # noqa: A002
        return _FakeResp(server_response)

    with patch("minions.tools.await_events.httpx.get", side_effect=fake_get):
        result = await_events()

    payload = result["events"][0]["event"]["payload"]
    assert payload["file"] == f"{proj}{os.sep}notes.md"
    assert PROJECT_DIR_PLACEHOLDER not in payload["file"]
