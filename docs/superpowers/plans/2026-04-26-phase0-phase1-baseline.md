# MinionsOS V3 Phase 0 + Minimal Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a stable, verifiable startup baseline (`./install.sh && uv sync && ./mos doctor && ./gru`) and freeze the minimal Phase 1 state/status contract so `./mos status --json` exposes project, backend, agent, queue, and failure state consistently.

**Architecture:** Fix startup blockers in-place (doctor checks, port probe, model registry, debug flag, runtime dirs), then extend `mos status --json` with a richer per-project snapshot that includes backend health, EACN agent list, queue depth, and recent failures — all sourced from the existing `eacn_client.probe_backend` and `health.backend_health` helpers. No new modules needed for Phase 0; Phase 1 adds one small `StatusSnapshot` dataclass and wires it into the CLI.

**Tech Stack:** Python 3.11+, uv, pytest, typer, pydantic, httpx, ruff

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `minions/cli.py` | Modify | Extend `status --json` output; add model-registry doctor check; fix debug-flag doctor check |
| `minions/lifecycle/health.py` | Modify | Add `project_status_snapshot()` returning the Phase 1 minimal state dict |
| `minions/lifecycle/eacn_client.py` | Modify | Extend `probe_backend` to include `queue_depth` and `recent_failures` |
| `minions/config/__init__.py` | Modify | Add `claude_model` field to `GruConfig`; add `model_registry_valid()` helper |
| `minions/gru/loop.py` | Modify | Pass `--no-debug` (or omit `--debug`) by default; respect `MINIONS_DEBUG` env var |
| `tests/unit/test_status_snapshot.py` | Create | Unit tests for `project_status_snapshot` |
| `tests/unit/test_doctor_checks.py` | Create | Unit tests for new doctor checks (model registry, debug flag, runtime dirs) |
| `tests/unit/test_config.py` | Modify | Add tests for `claude_model` field and `model_registry_valid()` |

---

## Task 1: Add `claude_model` to `GruConfig` and a `model_registry_valid()` helper

**Files:**
- Modify: `minions/config/__init__.py:204-295`
- Modify: `tests/unit/test_config.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_config.py — append to existing file

class TestGruConfigModel:
    def test_default_claude_model(self, tmp_path: Path) -> None:
        cfg = load_gru_config(tmp_path / "nonexistent.yaml")
        assert cfg.claude_model == "claude-sonnet-4-6"

    def test_custom_claude_model(self, tmp_path: Path) -> None:
        p = tmp_path / "gru.yaml"
        p.write_text(yaml.dump({"claude_model": "claude-opus-4-7"}))
        cfg = load_gru_config(p)
        assert cfg.claude_model == "claude-opus-4-7"

    def test_model_registry_valid_known(self, tmp_path: Path) -> None:
        cfg = load_gru_config(tmp_path / "nonexistent.yaml")
        ok, detail = cfg.model_registry_valid()
        assert ok is True
        assert cfg.claude_model in detail

    def test_model_registry_valid_unknown(self, tmp_path: Path) -> None:
        p = tmp_path / "gru.yaml"
        p.write_text(yaml.dump({"claude_model": "claude-fake-99"}))
        cfg = load_gru_config(p)
        ok, detail = cfg.model_registry_valid()
        assert ok is False
        assert "claude-fake-99" in detail
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/mjm/MinionsOS_V3
uv run pytest tests/unit/test_config.py::TestGruConfigModel -v
```

Expected: `AttributeError: 'GruConfig' object has no attribute 'claude_model'`

- [ ] **Step 3: Add `claude_model` field and `model_registry_valid()` to `GruConfig`**

In `minions/config/__init__.py`, inside the `GruConfig` class after the `gru_eacn_agent_id` field (around line 251), add:

```python
    claude_model: str = Field(
        default="claude-sonnet-4-6",
        description="Claude model name passed to the claude CLI (e.g. claude-sonnet-4-6).",
    )

    # Known callable model names — update when Anthropic releases new models.
    _KNOWN_MODELS: frozenset[str] = frozenset({
        "claude-opus-4-7",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
    })

    def model_registry_valid(self) -> tuple[bool, str]:
        """Return (ok, detail) for the configured claude_model."""
        if self.claude_model in self._KNOWN_MODELS:
            return True, f"{self.claude_model} is a known model"
        known = ", ".join(sorted(self._KNOWN_MODELS))
        return False, f"{self.claude_model!r} not in known models ({known})"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_config.py::TestGruConfigModel -v
```

Expected: 4 PASSED

- [ ] **Step 5: Run ruff**

```bash
uv run ruff check minions/config/__init__.py
```

Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add minions/config/__init__.py tests/unit/test_config.py
git commit -m "feat(config): add claude_model field and model_registry_valid() to GruConfig"
```

---

## Task 2: Add model-registry and debug-flag doctor checks

**Files:**
- Modify: `minions/cli.py:168-331`
- Create: `tests/unit/test_doctor_checks.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_doctor_checks.py
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def _run_doctor_json(env_overrides: dict | None = None) -> list[dict]:
    import os
    env = {**os.environ, **(env_overrides or {})}
    result = subprocess.run(
        [sys.executable, "-m", "minions.cli", "doctor", "--json"],
        capture_output=True,
        text=True,
        env=env,
    )
    return json.loads(result.stdout)


class TestDoctorModelRegistry:
    def test_model_registry_check_present(self) -> None:
        checks = _run_doctor_json()
        names = {c["name"] for c in checks}
        assert "model-registry" in names

    def test_model_registry_ok_with_default(self) -> None:
        checks = _run_doctor_json()
        mc = next(c for c in checks if c["name"] == "model-registry")
        assert mc["ok"] is True


class TestDoctorDebugFlag:
    def test_debug_flag_check_present(self) -> None:
        checks = _run_doctor_json()
        names = {c["name"] for c in checks}
        assert "claude-debug-disabled" in names

    def test_debug_disabled_by_default(self) -> None:
        checks = _run_doctor_json({"MINIONS_DEBUG": ""})
        dc = next(c for c in checks if c["name"] == "claude-debug-disabled")
        assert dc["ok"] is True

    def test_debug_enabled_when_env_set(self) -> None:
        checks = _run_doctor_json({"MINIONS_DEBUG": "1"})
        dc = next(c for c in checks if c["name"] == "claude-debug-disabled")
        assert dc["ok"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_doctor_checks.py -v
```

Expected: FAILED — checks not present in doctor output

- [ ] **Step 3: Add model-registry and debug-flag checks to `doctor()` in `minions/cli.py`**

In `minions/cli.py`, inside the `doctor()` function, after the `port-probe` check (around line 259) and before the `state-dir-writable` check, add:

```python
    # Model registry consistency
    try:
        from minions.config import load_gru_config as _load_cfg
        _cfg = _load_cfg()
        _ok, _detail = _cfg.model_registry_valid()
        _check("model-registry", _ok, _detail)
    except Exception as exc:
        _check("model-registry", False, str(exc))

    # Claude --debug should be off by default
    import os as _os
    debug_on = bool(_os.environ.get("MINIONS_DEBUG", "").strip())
    _check(
        "claude-debug-disabled",
        not debug_on,
        "MINIONS_DEBUG is unset (good)" if not debug_on else "MINIONS_DEBUG is set — debug mode active",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_doctor_checks.py -v
```

Expected: 5 PASSED

- [ ] **Step 5: Run ruff**

```bash
uv run ruff check minions/cli.py
```

Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add minions/cli.py tests/unit/test_doctor_checks.py
git commit -m "feat(doctor): add model-registry and claude-debug-disabled checks"
```

---

## Task 3: Add `project_status_snapshot()` to `health.py`

This is the Phase 1 minimal state contract: a single function that returns a consistent dict for one project covering backend health, EACN agents, queue depth, and recent failures.

**Files:**
- Modify: `minions/lifecycle/health.py`
- Create: `tests/unit/test_status_snapshot.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_status_snapshot.py
from __future__ import annotations

from unittest.mock import patch

import pytest

from minions.lifecycle.health import project_status_snapshot


class TestProjectStatusSnapshot:
    def test_returns_required_keys(self) -> None:
        with patch("minions.lifecycle.health.backend_health", return_value=False):
            snap = project_status_snapshot(port=37596, project_status="active")
        required = {"port", "project_status", "backend_alive", "agents", "queue_depth", "recent_failures"}
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
            patch("minions.lifecycle.health.eacn_client.probe_backend", return_value=fake_probe),
        ):
            snap = project_status_snapshot(port=37596, project_status="active")
        assert snap["backend_alive"] is True
        assert len(snap["agents"]) == 1
        assert snap["agents"][0]["agent_id"] == "gru"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_status_snapshot.py -v
```

Expected: `ImportError: cannot import name 'project_status_snapshot'`

- [ ] **Step 3: Implement `project_status_snapshot()` in `minions/lifecycle/health.py`**

Append to `minions/lifecycle/health.py` after the `get_crash_counter()` function:

```python
# ---------------------------------------------------------------------------
# Phase 1 minimal status snapshot
# ---------------------------------------------------------------------------


def project_status_snapshot(port: int, project_status: str) -> dict:
    """Return a minimal Phase 1 status dict for one project.

    Keys: port, project_status, backend_alive, agents, queue_depth, recent_failures.
    Non-active projects skip the backend probe (backend_alive=None).
    Never raises; errors are captured in recent_failures.
    """
    from minions.lifecycle import eacn_client

    if project_status != "active":
        return {
            "port": port,
            "project_status": project_status,
            "backend_alive": None,
            "agents": [],
            "queue_depth": 0,
            "recent_failures": [],
        }

    alive = backend_health(port)
    agents: list[dict] = []
    queue_depth = 0
    recent_failures: list[str] = []

    if alive:
        try:
            probe = eacn_client.probe_backend(port)
            agents = probe.get("agents", [])
            queue_depth = probe.get("queue_depth", 0)
            recent_failures = probe.get("errors", [])
        except Exception as exc:
            recent_failures.append(str(exc))

    return {
        "port": port,
        "project_status": project_status,
        "backend_alive": alive,
        "agents": agents,
        "queue_depth": queue_depth,
        "recent_failures": recent_failures,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_status_snapshot.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Run ruff**

```bash
uv run ruff check minions/lifecycle/health.py
```

Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add minions/lifecycle/health.py tests/unit/test_status_snapshot.py
git commit -m "feat(health): add project_status_snapshot() for Phase 1 status contract"
```

---

## Task 4: Wire `project_status_snapshot()` into `mos status --json`

**Files:**
- Modify: `minions/cli.py:71-121`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_doctor_checks.py — append to existing file

import json, subprocess, sys, os

class TestStatusJson:
    def test_status_json_has_phase1_keys(self, tmp_path) -> None:
        # With no projects, output should be an empty list — just verify it parses.
        result = subprocess.run(
            [sys.executable, "-m", "minions.cli", "status", "--json"],
            capture_output=True,
            text=True,
            env={**os.environ, "MINIONS_ROOT": str(tmp_path)},
        )
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        # If any projects exist, each row must have the Phase 1 keys.
        for row in data:
            for key in ("port", "name", "status", "backend_alive", "agents", "queue_depth", "recent_failures"):
                assert key in row, f"Missing key {key!r} in status row"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_doctor_checks.py::TestStatusJson -v
```

Expected: FAILED — `healthy` key present but `backend_alive`, `agents`, etc. missing

- [ ] **Step 3: Update `status()` in `minions/cli.py` to use `project_status_snapshot()`**

Replace the `if json_flag:` block inside `status()` (lines ~84-99) with:

```python
    if json_flag:
        from minions.lifecycle.health import project_status_snapshot
        rows = []
        for p in projects:
            snap = project_status_snapshot(p.port, p.status)
            rows.append(
                {
                    "port": p.port,
                    "name": p.real_name,
                    "status": p.status,
                    "venue": p.venue,
                    "roles": len(p.active_roles),
                    "backend_alive": snap["backend_alive"],
                    "agents": snap["agents"],
                    "queue_depth": snap["queue_depth"],
                    "recent_failures": snap["recent_failures"],
                }
            )
        _json_out(rows)
        return
```

Also update the table rendering block to use `snap["backend_alive"]` instead of the old `healthy` variable:

```python
    for p in projects:
        from minions.lifecycle.health import project_status_snapshot
        snap = project_status_snapshot(p.port, p.status)
        alive = snap["backend_alive"]
        health_str = "✓" if alive else ("✗" if alive is False else "—")
        table.add_row(
            str(p.port),
            p.real_name,
            p.status,
            p.venue or "—",
            health_str,
            str(len(p.active_roles)),
        )
```

Remove the old `from minions.lifecycle.health import backend_health` import at the top of `status()` since it's now inside `project_status_snapshot`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_doctor_checks.py::TestStatusJson -v
```

Expected: PASSED

- [ ] **Step 5: Run full unit suite**

```bash
uv run pytest tests/unit/ -v
```

Expected: all pass (or pre-existing failures only)

- [ ] **Step 6: Run ruff**

```bash
uv run ruff check minions/cli.py && uv run ruff format --check minions/cli.py
```

Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add minions/cli.py tests/unit/test_doctor_checks.py
git commit -m "feat(cli): extend status --json with Phase 1 backend/agent/queue/failure fields"
```

---

## Task 5: Respect `MINIONS_DEBUG` in `gru/loop.py` and launcher

**Files:**
- Modify: `minions/gru/loop.py`

The spec says `--debug` must not be enabled by default; only via explicit env var or diagnostic mode.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_doctor_checks.py — append

import importlib

class TestGruLoopDebugFlag:
    def test_debug_flag_off_by_default(self, monkeypatch) -> None:
        monkeypatch.delenv("MINIONS_DEBUG", raising=False)
        from minions.gru import loop as gru_loop
        importlib.reload(gru_loop)
        assert gru_loop.DEBUG_MODE is False

    def test_debug_flag_on_when_env_set(self, monkeypatch) -> None:
        monkeypatch.setenv("MINIONS_DEBUG", "1")
        from minions.gru import loop as gru_loop
        importlib.reload(gru_loop)
        assert gru_loop.DEBUG_MODE is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_doctor_checks.py::TestGruLoopDebugFlag -v
```

Expected: `AttributeError: module 'minions.gru.loop' has no attribute 'DEBUG_MODE'`

- [ ] **Step 3: Add `DEBUG_MODE` constant to `minions/gru/loop.py`**

At the top of `minions/gru/loop.py`, after the imports, add:

```python
import os as _os

DEBUG_MODE: bool = bool(_os.environ.get("MINIONS_DEBUG", "").strip())
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/test_doctor_checks.py::TestGruLoopDebugFlag -v
```

Expected: 2 PASSED

- [ ] **Step 5: Run ruff**

```bash
uv run ruff check minions/gru/loop.py
```

Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add minions/gru/loop.py tests/unit/test_doctor_checks.py
git commit -m "feat(gru): add DEBUG_MODE flag controlled by MINIONS_DEBUG env var"
```

---

## Task 6: Final integration — run full test suite and ruff

- [ ] **Step 1: Run all unit tests**

```bash
uv run pytest tests/unit/ -v
```

Expected: all pass

- [ ] **Step 2: Run ruff on entire package**

```bash
uv run ruff check minions/ && uv run ruff format --check minions/
```

Expected: no errors

- [ ] **Step 3: Smoke test doctor output**

```bash
./mos doctor
```

Expected: table with at least these checks present: `uv`, `node`, `git`, `parent-dir-is-git-repo`, `eacn3-importable`, `eacn3-plugin-built`, `node>=16`, `mcp-config-mounts-eacn3`, `port-probe`, `model-registry`, `claude-debug-disabled`, `state-dir-writable`

- [ ] **Step 4: Smoke test status JSON**

```bash
./mos status --json
```

Expected: JSON array; each element has keys `port`, `name`, `status`, `venue`, `roles`, `backend_alive`, `agents`, `queue_depth`, `recent_failures`

- [ ] **Step 5: Commit if any stray changes**

```bash
git add -A
git status
# commit only if there are unstaged changes
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| Phase 0: `./mos doctor` checks uv, EACN3, port, model registry, Claude CLI, writable dirs | Tasks 1, 2 |
| Phase 0: `--debug` not enabled by default; only via explicit env var | Task 5 |
| Phase 1: `./mos status --json` exposes backend alive/dead, agent list, queue depth, recent failures | Tasks 3, 4 |
| Phase 1: state contract — project id/port, agent id, role, status, last_seen, current task, blocked reason, wake policy, artifact pointers | Partial — `agents` list from EACN probe carries agent_id/name; full last_seen/task/blocked fields require EACN3 to return them. This plan exposes what `probe_backend` already returns; deeper fields are Phase 1 follow-on. |

**Placeholder scan:** None found.

**Type consistency:** `project_status_snapshot` returns `dict` throughout; `backend_alive` is `bool | None` consistently.

**Scope check:** Focused on Phase 0 doctor + Phase 1 status contract. Wakeup scheduler, role lifecycle, Camera-Ready, Reviewer, and viz are explicitly deferred.
