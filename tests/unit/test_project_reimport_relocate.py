"""Tests for project_reimport / project_relocate (issue #41)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from minions.errors import ProjectError
from minions.lifecycle.project import project_reimport, project_relocate
from minions.state.store import ProjectEntry, StateStore


@pytest.fixture
def projects_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(root))
    return root


def _make_meta(project_dir: Path, port: int, **overrides: object) -> dict[str, object]:
    project_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "port": port,
        "real_name": f"project-{port}",
        "status": "active",  # should be forced to dormant on reimport
        "created": "2025-01-01T00:00:00+00:00",
        "workspace_root": str(project_dir),
        "workspace_main": str(project_dir / "branches" / "main"),
        "workspace_roles_root": str(project_dir / "branches"),
        "workspace_shared": str(project_dir / "branches" / "shared"),
        "active_roles": [],
    }
    payload.update(overrides)
    (project_dir / "meta.json").write_text(json.dumps(payload), encoding="utf-8")
    return payload


# ------------------------- reimport -------------------------


def test_reimport_happy_path(projects_root: Path, tmp_path: Path) -> None:
    port = 39100
    pdir = projects_root / f"project_{port}"
    _make_meta(pdir, port)
    store = StateStore(root=tmp_path / "state")

    entry = project_reimport(port, store=store)

    assert entry.port == port
    assert entry.status == "dormant"
    assert entry.real_name == f"project-{port}"
    assert store.get_project(port) is not None


def test_reimport_rejects_existing_entry(projects_root: Path, tmp_path: Path) -> None:
    port = 39101
    pdir = projects_root / f"project_{port}"
    _make_meta(pdir, port)
    store = StateStore(root=tmp_path / "state")
    store.add_project(
        ProjectEntry(
            port=port,
            real_name=f"project-{port}",
            status="dormant",
            created="2025-01-01T00:00:00+00:00",
        )
    )
    with pytest.raises(ProjectError, match="already registered"):
        project_reimport(port, store=store)


def test_reimport_missing_meta(projects_root: Path, tmp_path: Path) -> None:
    port = 39102
    (projects_root / f"project_{port}").mkdir()
    store = StateStore(root=tmp_path / "state")
    with pytest.raises(ProjectError, match=r"meta\.json missing"):
        project_reimport(port, store=store)


# ------------------------- relocate -------------------------


def _register_dormant(
    store: StateStore, port: int, project_dir: Path, status: str = "dormant"
) -> None:
    store.add_project(
        ProjectEntry(
            port=port,
            real_name=f"project-{port}",
            status=status,  # type: ignore[arg-type]
            created="2025-01-01T00:00:00+00:00",
            workspace_root=str(project_dir),
            workspace_main=str(project_dir / "branches" / "main"),
            workspace_roles_root=str(project_dir / "branches"),
            workspace_shared=str(project_dir / "branches" / "shared"),
        )
    )


def test_relocate_happy_path(
    projects_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = 39200
    pdir = projects_root / f"project_{port}"
    _make_meta(pdir, port)

    # draft.json with a path-typed field plus a non-path string (must NOT change).
    draft_dir = pdir / "branches" / "shared" / "draft"
    draft_dir.mkdir(parents=True)
    (draft_dir / "draft.json").write_text(
        json.dumps(
            {
                "workspace": str(pdir / "branches" / "main"),
                "summary": "This description references the project but is not a path.",
            }
        ),
        encoding="utf-8",
    )

    # agent_map.json
    eacn = pdir / "eacn3_data"
    eacn.mkdir(parents=True)
    (eacn / "agent_map.json").write_text(
        json.dumps({"home": str(pdir / "branches" / "alpha")}),
        encoding="utf-8",
    )

    # Sidestep git verification.
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(args=a, returncode=0, stdout="", stderr=""),
    )

    store = StateStore(root=tmp_path / "state")
    _register_dormant(store, port, pdir)

    new_path = tmp_path / "relocated" / f"project_{port}"
    entry = project_relocate(port, new_path, store=store)

    assert entry.status == "dormant"
    assert new_path.exists()
    assert not pdir.exists()

    new_meta = json.loads((new_path / "meta.json").read_text(encoding="utf-8"))
    assert new_meta["workspace_root"] == str(new_path)
    assert new_meta["workspace_main"] == str(new_path / "branches" / "main")

    new_draft = json.loads(
        (new_path / "branches" / "shared" / "draft" / "draft.json").read_text(encoding="utf-8")
    )
    assert new_draft["workspace"] == str(new_path / "branches" / "main")
    assert new_draft["summary"] == "This description references the project but is not a path."

    new_map = json.loads((new_path / "eacn3_data" / "agent_map.json").read_text(encoding="utf-8"))
    assert new_map["home"] == str(new_path / "branches" / "alpha")

    refreshed = store.get_project(port)
    assert refreshed is not None
    assert refreshed.workspace_root == str(new_path)


def test_relocate_refuses_non_dormant(projects_root: Path, tmp_path: Path) -> None:
    port = 39201
    pdir = projects_root / f"project_{port}"
    _make_meta(pdir, port)
    store = StateStore(root=tmp_path / "state")
    _register_dormant(store, port, pdir, status="active")
    with pytest.raises(ProjectError, match="requires 'dormant'"):
        project_relocate(port, tmp_path / "elsewhere", store=store)


def test_relocate_refuses_when_target_exists(projects_root: Path, tmp_path: Path) -> None:
    port = 39202
    pdir = projects_root / f"project_{port}"
    _make_meta(pdir, port)
    store = StateStore(root=tmp_path / "state")
    _register_dormant(store, port, pdir)
    target = tmp_path / "existing"
    target.mkdir()
    with pytest.raises(ProjectError, match="already exists"):
        project_relocate(port, target, store=store)
