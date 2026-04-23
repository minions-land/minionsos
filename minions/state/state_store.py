"""Dict-based StateStore facade used by unit tests and legacy callers.

The canonical implementation lives in ``minions.state.store`` (Pydantic-based).
This module provides a simpler dict-in / dict-out API that the test suite
exercises directly.
"""
from __future__ import annotations

import fcntl
import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Literal

from minions.errors import PortError, StateError
from minions.state.port_allocator import PortAllocator

logger = logging.getLogger(__name__)

PORT_MIN = 37596
PORT_MAX = 37999

# Module-level threading lock for in-process safety.
# fcntl handles cross-process safety.
_THREAD_LOCK = threading.Lock()


class StateStore:
    """Thread- and process-safe store for ``projects.json`` (dict-based API)."""

    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            from minions.paths import STATE_DIR
            root = STATE_DIR
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._path = self._root / "projects.json"
        self._lock_path = self._root / "projects.lock"
        self._allocator = PortAllocator(PORT_MIN, PORT_MAX)

    # ------------------------------------------------------------------
    # Low-level I/O
    # ------------------------------------------------------------------

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"projects": [], "retired_ports": []}
        try:
            raw = self._path.read_text(encoding="utf-8").strip()
            return json.loads(raw) if raw else {"projects": [], "retired_ports": []}
        except Exception as exc:
            raise StateError(f"Failed to parse {self._path}: {exc}") from exc

    def _write_atomic(self, data: dict[str, Any]) -> None:
        """Write *data* atomically using a temp file in the same directory."""
        dir_path = self._path.parent
        try:
            fd, tmp_path_str = tempfile.mkstemp(dir=str(dir_path), suffix=".tmp")
            tmp_path = Path(tmp_path_str)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, indent=2)
                os.replace(tmp_path, self._path)
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise
        except OSError as exc:
            raise StateError(f"Failed to write {self._path}: {exc}") from exc

    def _with_lock(self, fn: Any) -> Any:
        """Execute *fn(data) -> data | None* under thread + file lock.

        Uses a separate lock file so that ``os.replace`` on the data file
        does not invalidate open file handles held by other threads/processes.
        """
        with _THREAD_LOCK:
            # Also acquire a cross-process file lock.
            self._lock_path.touch(exist_ok=True)
            with self._lock_path.open("r+", encoding="utf-8") as lock_fh:
                fcntl.flock(lock_fh, fcntl.LOCK_EX)
                try:
                    data = self._read()
                    result = fn(data)
                    if result is not None:
                        self._write_atomic(result)
                finally:
                    fcntl.flock(lock_fh, fcntl.LOCK_UN)

    # ------------------------------------------------------------------
    # Public API (dict-based)
    # ------------------------------------------------------------------

    def add_project(self, project: dict[str, Any]) -> None:
        """Append *project* dict to the store.

        Raises ``StateError`` if a project with the same port already exists.
        """
        def _add(data: dict[str, Any]) -> dict[str, Any]:
            port = project["port"]
            if any(p["port"] == port for p in data["projects"]):
                raise StateError(f"Project with port {port} already exists.")
            data["projects"].append(project)
            return data

        self._with_lock(_add)

    def get_project(self, port: int) -> dict[str, Any] | None:
        """Return the project dict for *port*, or ``None`` if absent."""
        data = self._read()
        for p in data["projects"]:
            if p["port"] == port:
                return p
        return None

    def update_project(self, port: int, **fields: Any) -> dict[str, Any]:
        """Update fields on the project identified by *port*."""
        result: dict[str, Any] | None = None

        def _update(data: dict[str, Any]) -> dict[str, Any]:
            nonlocal result
            for i, p in enumerate(data["projects"]):
                if p["port"] == port:
                    p.update(fields)
                    data["projects"][i] = p
                    result = p
                    return data
            raise StateError(f"Project with port {port} not found.")

        self._with_lock(_update)
        if result is None:
            raise StateError(f"Project with port {port} not found.")
        return result

    def list_projects(
        self,
        status: Literal["all", "active", "dormant", "closed"] | None = None,
    ) -> list[dict[str, Any]]:
        """Return projects, optionally filtered by *status*."""
        data = self._read()
        projects = data["projects"]
        if status and status != "all":
            projects = [p for p in projects if p.get("status") == status]
        return list(projects)

    def retire_port(self, port: int) -> None:
        """Mark *port* as permanently retired."""
        def _retire(data: dict[str, Any]) -> dict[str, Any] | None:
            if port not in data["retired_ports"]:
                data["retired_ports"].append(port)
                return data
            return None  # no-op

        self._with_lock(_retire)

    def is_port_retired(self, port: int) -> bool:
        """Return True if *port* has been retired."""
        data = self._read()
        return port in data["retired_ports"]

    def find_next_port(self) -> int:
        """Find the next free port via bind-probe, skipping retired ports."""
        data = self._read()
        retired: set[int] = set(data["retired_ports"])
        used: set[int] = {
            p["port"] for p in data["projects"] if p.get("status") != "closed"
        }
        excluded = retired | used
        return self._allocator.allocate(excluded)
