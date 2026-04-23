"""Atomic, file-locked state store for ``minions/state/projects.json``.

Design:
- All writes go through ``_write_atomic``: write to ``.tmp`` then ``os.replace``.
- Cross-process safety via ``fcntl.flock`` (exclusive lock on the JSON file).
- Port allocation uses a bind-probe to guarantee the port is actually free.
- Retired ports are tracked permanently so they are never reused.
"""
from __future__ import annotations

import fcntl
import json
import logging
import os
import socket
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from minions.errors import PortError, StateError
from minions.paths import PROJECTS_JSON

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Port range
# ---------------------------------------------------------------------------

PORT_MIN = 37596
PORT_MAX = 37999

# ---------------------------------------------------------------------------
# Pydantic models for projects.json
# ---------------------------------------------------------------------------


class RoleEntry(BaseModel):
    name: str
    state: Literal["active", "sleeping", "dismissed"]
    pid: int | None = None
    spawned_at: str | None = None
    poll_interval: str | None = None


class ProjectEntry(BaseModel):
    port: int
    real_name: str
    status: Literal["active", "dormant", "closed"]
    created: str
    dormant_at: str | None = None
    closed_at: str | None = None
    venue: str | None = None
    upstream_branch: str = "main"
    current_branch: str = ""
    active_roles: list[RoleEntry] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class ProjectsData(BaseModel):
    projects: list[ProjectEntry] = Field(default_factory=list)
    retired_ports: list[int] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _bind_probe(port: int) -> bool:
    """Return True if *port* can be bound (i.e. is free)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# StateStore
# ---------------------------------------------------------------------------


class StateStore:
    """Thread- and process-safe store for ``projects.json``.

    Usage::

        store = StateStore()
        port = store.find_next_port()
        store.add_project(ProjectEntry(port=port, ...))
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path: Path = path or PROJECTS_JSON
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Low-level I/O
    # ------------------------------------------------------------------

    @contextmanager
    def _locked(self, mode: str = "r+") -> Generator[Any, None, None]:
        """Open the JSON file with an exclusive flock, yielding the file object.

        Creates the file with an empty structure if it does not exist.
        """
        if not self._path.exists():
            self._path.write_text(
                json.dumps({"projects": [], "retired_ports": []}, indent=2),
                encoding="utf-8",
            )

        with self._path.open(mode, encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield fh
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def _read_data(self) -> ProjectsData:
        """Read and parse projects.json (no lock — caller must hold lock or use _locked)."""
        if not self._path.exists():
            return ProjectsData()
        try:
            raw = self._path.read_text(encoding="utf-8").strip()
            if not raw:
                return ProjectsData()
            return ProjectsData.model_validate_json(raw)
        except Exception as exc:
            raise StateError(f"Failed to parse {self._path}: {exc}") from exc

    def _write_atomic(self, data: ProjectsData) -> None:
        """Write *data* atomically (tmp + rename) — caller must hold lock."""
        tmp = self._path.with_suffix(".tmp")
        try:
            tmp.write_text(data.model_dump_json(indent=2), encoding="utf-8")
            os.replace(tmp, self._path)
        except OSError as exc:
            raise StateError(f"Failed to write {self._path}: {exc}") from exc
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> ProjectsData:
        """Return a snapshot of the current projects data (no lock held)."""
        return self._read_data()

    def add_project(self, entry: ProjectEntry) -> None:
        """Append *entry* to projects.json.

        Raises ``StateError`` if a project with the same port already exists.
        """
        with self._locked("r+") as fh:
            raw = fh.read()
            data = ProjectsData.model_validate_json(raw) if raw.strip() else ProjectsData()
            if any(p.port == entry.port for p in data.projects):
                raise StateError(f"Project with port {entry.port} already exists.")
            data.projects.append(entry)
            self._write_atomic(data)
        logger.debug("add_project port=%d name=%r", entry.port, entry.real_name)

    def update_project(self, port: int, **fields: Any) -> ProjectEntry:
        """Update fields on the project identified by *port*.

        Returns the updated ``ProjectEntry``.  Raises ``StateError`` if not found.
        """
        with self._locked("r+") as fh:
            raw = fh.read()
            data = ProjectsData.model_validate_json(raw) if raw.strip() else ProjectsData()
            for i, p in enumerate(data.projects):
                if p.port == port:
                    updated = p.model_copy(update=fields)
                    data.projects[i] = updated
                    self._write_atomic(data)
                    logger.debug("update_project port=%d fields=%s", port, list(fields))
                    return updated
        raise StateError(f"Project with port {port} not found.")

    def get_project(self, port: int) -> ProjectEntry | None:
        """Return the project entry for *port*, or ``None`` if absent."""
        data = self._read_data()
        for p in data.projects:
            if p.port == port:
                return p
        return None

    def list_projects(
        self,
        filter: Literal["all", "active", "dormant", "closed"] = "all",
    ) -> list[ProjectEntry]:
        """Return projects matching *filter*."""
        data = self._read_data()
        if filter == "all":
            return list(data.projects)
        return [p for p in data.projects if p.status == filter]

    def retire_port(self, port: int) -> None:
        """Mark *port* as permanently retired (used by project_close)."""
        with self._locked("r+") as fh:
            raw = fh.read()
            data = ProjectsData.model_validate_json(raw) if raw.strip() else ProjectsData()
            if port not in data.retired_ports:
                data.retired_ports.append(port)
                self._write_atomic(data)
        logger.debug("retire_port port=%d", port)

    def find_next_port(self) -> int:
        """Find the next free port in [PORT_MIN, PORT_MAX] via bind-probe.

        Skips ports already in use by active/dormant projects and permanently
        retired ports.

        Raises ``PortError`` if no free port is available.
        """
        data = self._read_data()
        used_ports: set[int] = {p.port for p in data.projects if p.status != "closed"}
        retired: set[int] = set(data.retired_ports)
        excluded = used_ports | retired

        for port in range(PORT_MIN, PORT_MAX + 1):
            if port in excluded:
                continue
            if _bind_probe(port):
                logger.debug("find_next_port → %d", port)
                return port
            # Port is in use by something else on the system; skip.

        raise PortError(f"No free port available in range {PORT_MIN}-{PORT_MAX}.")

    # ------------------------------------------------------------------
    # Role helpers (convenience wrappers around update_project)
    # ------------------------------------------------------------------

    def upsert_role(self, port: int, role: RoleEntry) -> None:
        """Insert or replace a role entry in the project's ``active_roles`` list."""
        with self._locked("r+") as fh:
            raw = fh.read()
            data = ProjectsData.model_validate_json(raw) if raw.strip() else ProjectsData()
            for i, p in enumerate(data.projects):
                if p.port == port:
                    roles = [r for r in p.active_roles if r.name != role.name]
                    roles.append(role)
                    updated = p.model_copy(update={"active_roles": roles})
                    data.projects[i] = updated
                    self._write_atomic(data)
                    return
        raise StateError(f"Project with port {port} not found.")

    def remove_role(self, port: int, role_name: str) -> None:
        """Remove a role entry from the project's ``active_roles`` list."""
        with self._locked("r+") as fh:
            raw = fh.read()
            data = ProjectsData.model_validate_json(raw) if raw.strip() else ProjectsData()
            for i, p in enumerate(data.projects):
                if p.port == port:
                    roles = [r for r in p.active_roles if r.name != role_name]
                    updated = p.model_copy(update={"active_roles": roles})
                    data.projects[i] = updated
                    self._write_atomic(data)
                    return
        raise StateError(f"Project with port {port} not found.")
