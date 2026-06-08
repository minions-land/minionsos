"""Repository hygiene checks for runtime-only local artifacts."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _tracked_files() -> list[Path]:
    proc = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [Path(line) for line in proc.stdout.splitlines() if line]


def test_runtime_project_state_is_not_tracked() -> None:
    offenders: list[str] = []
    for rel in _tracked_files():
        text = rel.as_posix()
        if text.startswith(("projects/", "project_")):
            offenders.append(text)
            continue
        if "parent_repo.git" in rel.parts or "eacn3_data" in rel.parts:
            offenders.append(text)
            continue
        if text.startswith("minions/state/") and rel.name not in {
            "__init__.py",
            "port_allocator.py",
            "store.py",
        }:
            offenders.append(text)

    assert offenders == []


def test_local_config_and_runtime_locks_are_not_tracked() -> None:
    offenders: list[str] = []
    for rel in _tracked_files():
        text = rel.as_posix()
        if text == ".mcp.json":
            offenders.append(text)
            continue
        if (
            text.startswith("minions/config/")
            and rel.suffix in {".yaml", ".yml"}
            and not text.endswith((".yaml.example", ".yml.example"))
        ):
            offenders.append(text)
            continue
        if rel.suffix in {".pid", ".log"} or rel.name in {"projects.lock"}:
            offenders.append(text)

    assert offenders == []
