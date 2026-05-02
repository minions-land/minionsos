"""Atomic, file-locked state store for ``minions/state/projects.json``.

Design:
- Cross-process safety via ``fcntl.flock`` on a **separate lockfile**
  (``projects.lock``), not on the data file. ``os.replace`` swaps inodes on
  the data file, which would silently desync ``flock`` holders if we locked
  the data file directly. Locking a stable inode fixes this.
- In-process safety via a ``threading.Lock`` instance per ``StateStore``
  (plus a module-level lock so concurrent ``StateStore()`` instances that
  point at the same default path also serialize).
- All writes go through ``_write_atomic``: write to a sibling ``.tmp`` in
  the same directory then ``os.replace`` onto the data file.
- Port allocation uses a bind-probe to guarantee the port is actually free.
- Retired ports are tracked permanently so they are never reused.
"""

from __future__ import annotations

import fcntl
import logging
import os
import tempfile
import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TypedDict, TypeVar

from pydantic import BaseModel, Field

from minions.errors import PortError, StateError
from minions.paths import PROJECTS_JSON
from minions.state.port_allocator import PORT_MAX, PORT_MIN, PortAllocator

logger = logging.getLogger(__name__)

# Module-level lock to serialize in-process writers that share the default
# projects.json path across threads, even across distinct StateStore() objects.
_GLOBAL_THREAD_LOCK = threading.Lock()

T = TypeVar("T")


class RoleEntry(BaseModel):
    name: str
    state: Literal["active", "sleeping", "dismissed"]
    pid: int | None = None
    spawned_at: str | None = None
    session_name: str | None = None
    session_resumable: bool = False
    workspace_path: str | None = None
    workspace_branch: str | None = None
    github_push_target: str | None = None
    poll_interval: str | None = None
    eacn_agent_id: str | None = None
    eacn_agent_token: str | None = None
    eacn_registered_at: str | None = None
    last_seen: str | None = None
    current_task: str | None = None
    blocked_reason: str | None = None
    wake_policy: Literal["event", "time", "human", "any"] = "event"
    time_trigger_interval: str | None = None
    artifact_pointers: list[str] = Field(default_factory=list)


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
    workspace_root: str | None = None
    workspace_main: str | None = None
    workspace_roles_root: str | None = None
    workspace_shared: str | None = None
    github_push_target: str | None = None
    github_push_branch_prefix: str | None = None
    current_phase: str | None = None
    phase_version: int = 0
    phase_allowed_roles: list[str] = Field(default_factory=list)
    phase_updated_at: str | None = None
    phase_reason: str | None = None
    active_roles: list[RoleEntry] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class ProjectPhaseSnapshot(TypedDict):
    current_phase: str | None
    phase_version: int
    phase_allowed_roles: list[str]
    phase_online_roles: list[str]


class ProjectsData(BaseModel):
    projects: list[ProjectEntry] = Field(default_factory=list)
    retired_ports: list[int] = Field(default_factory=list)


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _bind_probe(port: int) -> bool:
    """Return True if *port* can be bound (i.e. is free).

    Delegated to ``PortAllocator`` so there is one canonical probe.
    """
    return PortAllocator(PORT_MIN, PORT_MAX)._is_free(port)


class StateStore:
    """Thread- and process-safe store for ``projects.json``.

    Accepts either ``path=<file>`` (canonical callers) or ``root=<dir>``
    (legacy dict-API callers migrated from the removed ``state_store``
    module, where the data file is ``root/projects.json``).
    """

    def __init__(
        self,
        path: Path | None = None,
        *,
        root: Path | None = None,
    ) -> None:
        if path is not None and root is not None:
            raise ValueError("StateStore: pass either 'path' or 'root', not both.")
        if root is not None:
            root.mkdir(parents=True, exist_ok=True)
            self._path: Path = root / "projects.json"
        else:
            self._path = path or PROJECTS_JSON
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path: Path = self._path.with_name(self._path.stem + ".lock")
        self._thread_lock = threading.Lock()
        self._allocator = PortAllocator(PORT_MIN, PORT_MAX)

    # ------------------------------------------------------------------
    # Low-level I/O — lockfile + thread lock
    # ------------------------------------------------------------------

    @contextmanager
    def _locked(self) -> Generator[None, None, None]:
        """Acquire thread lock then exclusive flock on the **lockfile**.

        Locking a separate, stable-inode lockfile is critical: ``os.replace``
        on the data file would otherwise swap the inode out from under other
        processes still holding an flock on the old inode, producing torn
        writes.
        """
        self._lock_path.touch(exist_ok=True)
        with (
            _GLOBAL_THREAD_LOCK,
            self._thread_lock,
            self._lock_path.open("r+", encoding="utf-8") as lock_fh,
        ):
            fcntl.flock(lock_fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_fh, fcntl.LOCK_UN)

    def _read_data(self) -> ProjectsData:
        """Read and parse projects.json. Callers may invoke with or without lock."""
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
        """Write *data* atomically via tmp-in-same-dir + ``os.replace``.

        Uses ``tempfile.mkstemp`` so concurrent writers never race on a
        shared ``.tmp`` name. Caller must hold ``_locked()``.
        """
        dir_path = self._path.parent
        fd, tmp_path_str = tempfile.mkstemp(dir=str(dir_path), suffix=".tmp")
        tmp_path = Path(tmp_path_str)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(data.model_dump_json(indent=2))
            os.replace(tmp_path, self._path)
        except OSError as exc:
            tmp_path.unlink(missing_ok=True)
            raise StateError(f"Failed to write {self._path}: {exc}") from exc
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    def _mutate(self, fn: Callable[[ProjectsData], T]) -> T:
        """Run *fn(data) -> result* under lock; persist ``data`` afterward."""
        with self._locked():
            data = self._read_data()
            result = fn(data)
            self._write_atomic(data)
            return result

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> ProjectsData:
        """Return a snapshot of the current projects data (no lock held)."""
        return self._read_data()

    def add_project(self, entry: ProjectEntry | dict[str, Any]) -> None:
        """Append *entry* to projects.json.

        Accepts a ``ProjectEntry`` (canonical) or a ``dict`` (legacy dict API
        from the removed ``state_store`` module).

        Raises ``StateError`` if a project with the same port already exists.
        """
        model = entry if isinstance(entry, ProjectEntry) else ProjectEntry.model_validate(entry)

        def _add(data: ProjectsData) -> None:
            if any(p.port == model.port for p in data.projects):
                raise StateError(f"Project with port {model.port} already exists.")
            data.projects.append(model)

        self._mutate(_add)
        logger.debug("add_project port=%d name=%r", model.port, model.real_name)

    def update_project(self, port: int, **fields: Any) -> ProjectEntry:
        """Update fields on the project identified by *port*. Raises if missing."""

        def _update(data: ProjectsData) -> ProjectEntry:
            for i, p in enumerate(data.projects):
                if p.port == port:
                    updated = p.model_copy(update=fields)
                    data.projects[i] = updated
                    return updated
            raise StateError(f"Project with port {port} not found.")

        updated = self._mutate(_update)
        logger.debug("update_project port=%d fields=%s", port, list(fields))
        return updated

    def get_project(self, port: int) -> ProjectEntry | None:
        """Return the project entry for *port*, or ``None`` if absent."""
        data = self._read_data()
        for p in data.projects:
            if p.port == port:
                return p
        return None

    def list_projects(
        self,
        filter: Literal["all", "active", "dormant", "closed"] | None = None,
        *,
        status: Literal["all", "active", "dormant", "closed"] | None = None,
    ) -> list[ProjectEntry]:
        """Return projects matching ``filter`` (or the legacy ``status`` kwarg)."""
        sel = status if status is not None else (filter if filter is not None else "all")
        data = self._read_data()
        if sel == "all":
            return list(data.projects)
        return [p for p in data.projects if p.status == sel]

    def retire_port(self, port: int) -> None:
        """Mark *port* as permanently retired (used by project_close)."""

        def _retire(data: ProjectsData) -> None:
            if port not in data.retired_ports:
                data.retired_ports.append(port)

        self._mutate(_retire)
        logger.debug("retire_port port=%d", port)

    def is_port_retired(self, port: int) -> bool:
        """Return True if *port* has been retired."""
        return port in self._read_data().retired_ports

    def find_next_port(self) -> int:
        """Find the next free port via bind-probe, skipping retired/in-use ports."""
        data = self._read_data()
        used_ports: set[int] = {p.port for p in data.projects if p.status != "closed"}
        retired: set[int] = set(data.retired_ports)
        excluded = used_ports | retired
        try:
            port = self._allocator.allocate(excluded)
        except PortError:
            raise PortError(f"No free port available in range {PORT_MIN}-{PORT_MAX}.") from None
        logger.debug("find_next_port → %d", port)
        return port

    # ------------------------------------------------------------------
    # Role helpers
    # ------------------------------------------------------------------

    def upsert_role(self, port: int, role: RoleEntry) -> None:
        """Insert or replace a role entry in the project's ``active_roles`` list."""

        def _upsert(data: ProjectsData) -> None:
            for i, p in enumerate(data.projects):
                if p.port == port:
                    roles = [r for r in p.active_roles if r.name != role.name]
                    roles.append(role)
                    data.projects[i] = p.model_copy(update={"active_roles": roles})
                    return
            raise StateError(f"Project with port {port} not found.")

        self._mutate(_upsert)

    def remove_role(self, port: int, role_name: str) -> None:
        """Remove a role entry from the project's ``active_roles`` list."""

        def _remove(data: ProjectsData) -> None:
            for i, p in enumerate(data.projects):
                if p.port == port:
                    roles = [r for r in p.active_roles if r.name != role_name]
                    data.projects[i] = p.model_copy(update={"active_roles": roles})
                    return
            raise StateError(f"Project with port {port} not found.")

        self._mutate(_remove)

    def touch_role_last_seen(self, port: int, role_name: str) -> None:
        """Update ``last_seen`` timestamp on a role entry."""

        def _touch(data: ProjectsData) -> None:
            for i, p in enumerate(data.projects):
                if p.port == port:
                    roles = list(p.active_roles)
                    for j, r in enumerate(roles):
                        if r.name == role_name:
                            roles[j] = r.model_copy(
                                update={"last_seen": _now_iso()},
                            )
                            break
                    data.projects[i] = p.model_copy(
                        update={"active_roles": roles},
                    )
                    return

        self._mutate(_touch)

    def update_role_task(
        self,
        port: int,
        role_name: str,
        current_task: str | None = None,
        blocked_reason: str | None = None,
    ) -> None:
        """Update ``current_task`` and/or ``blocked_reason`` on a role."""

        def _update(data: ProjectsData) -> None:
            for i, p in enumerate(data.projects):
                if p.port == port:
                    roles = list(p.active_roles)
                    for j, r in enumerate(roles):
                        if r.name == role_name:
                            updates: dict = {}
                            if current_task is not None:
                                updates["current_task"] = current_task
                            if blocked_reason is not None:
                                updates["blocked_reason"] = blocked_reason
                            if updates:
                                roles[j] = r.model_copy(update=updates)
                            break
                    data.projects[i] = p.model_copy(
                        update={"active_roles": roles},
                    )
                    return

        self._mutate(_update)
