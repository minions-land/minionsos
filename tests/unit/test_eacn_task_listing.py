"""Tests for project-local EACN task listing order."""

from __future__ import annotations

from types import SimpleNamespace

from eacn.network.api.routes import _sort_tasks


def test_eacn_api_sorts_tasks_newest_first_by_default() -> None:
    older = SimpleNamespace(id="older", created_at="2026-04-28 10:00:00")
    newer = SimpleNamespace(id="newer", created_at="2026-04-28T11:00:00+00:00")
    tasks = [older, newer]

    assert [task.id for task in _sort_tasks(tasks, "desc")] == ["newer", "older"]
    assert [task.id for task in _sort_tasks(tasks, "asc")] == ["older", "newer"]
