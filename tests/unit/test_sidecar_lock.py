"""Unit tests for the sidecar registry lock (sidecar_lock.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minions.lifecycle.sidecar_lock import allocate_session_id, lock_session_title


@pytest.fixture
def fake_claude_home(tmp_path: Path, monkeypatch):
    """Point CLAUDE_CONFIG_DIR at a temporary directory that exists."""
    home = tmp_path / "claude_home"
    home.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home))
    return home


@pytest.fixture
def missing_claude_home(tmp_path: Path, monkeypatch):
    """Point CLAUDE_CONFIG_DIR at a directory that does NOT exist."""
    missing = tmp_path / "absent"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(missing))
    assert not missing.exists()
    return missing


def test_allocate_session_id_is_uuid_string():
    """allocate_session_id should return a valid UUID4 string."""
    sid = allocate_session_id()
    import uuid

    parsed = uuid.UUID(sid)
    assert parsed.version == 4
    # No two ids should collide.
    assert sid != allocate_session_id()


def test_lock_session_title_writes_locked_row(fake_claude_home: Path):
    """Writes a locked row when the sidecar dir exists."""
    sid = "test-session-aaaa-bbbb-cccc-dddddddddddd"
    ok = lock_session_title(sid, "mos-12345-coder")
    assert ok is True

    path = fake_claude_home / "title-registry.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    entry = data[sid]
    assert entry["title"] == "mos-12345-coder"
    assert entry["locked"] is True
    assert entry["pending_auto_name"] is False
    assert entry["source"] == "minionsos"
    assert isinstance(entry["updated_at"], int)


def test_lock_session_title_noop_when_home_missing(missing_claude_home: Path):
    """Silent no-op when CLAUDE_CONFIG_DIR doesn't exist."""
    ok = lock_session_title("any-sid", "any-title")
    assert ok is False
    assert not missing_claude_home.exists()


def test_lock_session_title_merges_existing_entries(fake_claude_home: Path):
    """Concurrent locks should not clobber each other."""
    path = fake_claude_home / "title-registry.json"
    path.write_text(
        json.dumps(
            {
                "preexisting-sid": {
                    "title": "user-session",
                    "locked": True,
                    "source": "manual",
                }
            }
        ),
        encoding="utf-8",
    )

    sid = "fresh-mos-sid"
    assert lock_session_title(sid, "mos-9999-noter") is True

    data = json.loads(path.read_text(encoding="utf-8"))
    assert "preexisting-sid" in data
    assert data["preexisting-sid"]["title"] == "user-session"
    assert data[sid]["title"] == "mos-9999-noter"
    assert data[sid]["locked"] is True


def test_lock_session_title_overwrites_stale_entry(fake_claude_home: Path):
    """A re-spawn under the same sid should refresh the entry, not duplicate."""
    sid = "respawned-sid"
    assert lock_session_title(sid, "mos-1-coder") is True
    first = json.loads((fake_claude_home / "title-registry.json").read_text())[sid]

    # Re-lock with a new title.
    assert lock_session_title(sid, "mos-2-coder") is True
    second = json.loads((fake_claude_home / "title-registry.json").read_text())[sid]

    assert second["title"] == "mos-2-coder"
    assert second["locked"] is True
    assert second["updated_at"] >= first["updated_at"]


def test_lock_session_title_rejects_empty_inputs(fake_claude_home: Path):
    """Empty session_id or title is a programmer error; no-op."""
    assert lock_session_title("", "title") is False
    assert lock_session_title("sid", "") is False
    path = fake_claude_home / "title-registry.json"
    assert not path.exists()


def test_lock_session_title_handles_corrupt_registry(fake_claude_home: Path):
    """A corrupt registry must not crash the spawn — overwrite, don't raise."""
    path = fake_claude_home / "title-registry.json"
    path.write_text("not-valid-json {{", encoding="utf-8")

    sid = "fresh-sid"
    assert lock_session_title(sid, "mos-7-ethics") is True
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data[sid]["title"] == "mos-7-ethics"
