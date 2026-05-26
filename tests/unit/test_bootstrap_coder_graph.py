"""Unit tests for the Coder codegraph bootstrap.

The bootstrap runs `codegraph init -i` against the Coder branch's
worktree at register_role time. On a real codebase that takes 30-60s.
v15.51 D moved the heavy work to a daemon thread so register_role
returns immediately (the codegraph MCP launcher tolerates index-
missing).

Tests in this file:
- the daemon-thread default path returns immediately when the binary
  is present;
- the env-gated sync path still blocks for tools that need the index
  ready;
- a binary-missing path no-ops;
- a `.codegraph/` directory is treated as "already bootstrapped" and
  short-circuits the call;
- a failing init drops the operator-facing error marker.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from minions.lifecycle import project as project_mod


def _make_fake_cg_bin(tmp_path: Path) -> Path:
    """Create an executable stub at the path the bootstrap looks at.

    The bootstrap resolves the codegraph binary as
    ``MINIONS_ROOT/mcp-servers/codegraph/node_modules/.bin/codegraph``.
    We can't override MINIONS_ROOT mid-test cheaply, so instead the
    tests patch ``MINIONS_ROOT`` to ``tmp_path`` and create the stub
    at the resolved path.
    """
    cg_bin = tmp_path / "mcp-servers" / "codegraph" / "node_modules" / ".bin" / "codegraph"
    cg_bin.parent.mkdir(parents=True, exist_ok=True)
    cg_bin.write_text("#!/bin/sh\nexit 0\n")
    cg_bin.chmod(0o755)
    return cg_bin


class TestBootstrapCoderGraph:
    def test_async_default_returns_immediately(self, tmp_path: Path) -> None:
        """Default path: the daemon thread hides the subprocess latency."""
        os.environ.pop("MINIONS_BOOTSTRAP_CODER_GRAPH_SYNC", None)

        workspace = tmp_path / "branches" / "coder"
        workspace.mkdir(parents=True)
        _make_fake_cg_bin(tmp_path)

        slow_run_started = threading.Event()
        slow_run_done = threading.Event()

        def slow_subprocess_run(*args, **kwargs) -> subprocess.CompletedProcess:
            slow_run_started.set()
            time.sleep(0.3)
            slow_run_done.set()
            return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

        with (
            patch.object(project_mod, "MINIONS_ROOT", tmp_path),
            patch.object(project_mod.subprocess, "run", side_effect=slow_subprocess_run),
        ):
            t0 = time.monotonic()
            project_mod._bootstrap_coder_graph(workspace)
            elapsed = time.monotonic() - t0

        assert elapsed < 0.1, (
            f"_bootstrap_coder_graph blocked the caller; "
            f"elapsed={elapsed:.3f}s (expected <0.1s when async)."
        )
        # Daemon thread should still complete eventually.
        assert slow_run_started.wait(timeout=2.0), "daemon thread never started"
        assert slow_run_done.wait(timeout=2.0), "daemon thread never finished"

    def test_sync_env_blocks_caller(self, tmp_path: Path) -> None:
        """``MINIONS_BOOTSTRAP_CODER_GRAPH_SYNC=1`` reverts to blocking."""
        workspace = tmp_path / "branches" / "coder"
        workspace.mkdir(parents=True)
        _make_fake_cg_bin(tmp_path)

        def slow_subprocess_run(*args, **kwargs) -> subprocess.CompletedProcess:
            time.sleep(0.2)
            return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

        with (
            patch.object(project_mod, "MINIONS_ROOT", tmp_path),
            patch.object(project_mod.subprocess, "run", side_effect=slow_subprocess_run),
            patch.dict(os.environ, {"MINIONS_BOOTSTRAP_CODER_GRAPH_SYNC": "1"}),
        ):
            t0 = time.monotonic()
            project_mod._bootstrap_coder_graph(workspace)
            elapsed = time.monotonic() - t0

        assert elapsed >= 0.18, (
            f"sync mode should block on subprocess; elapsed={elapsed:.3f}s"
        )

    def test_skips_when_dot_codegraph_already_present(self, tmp_path: Path) -> None:
        """Idempotency contract: short-circuit if the index already exists."""
        workspace = tmp_path / "branches" / "coder"
        (workspace / ".codegraph").mkdir(parents=True)
        _make_fake_cg_bin(tmp_path)

        called = []

        def fake_run(*args, **kwargs) -> subprocess.CompletedProcess:
            called.append(args)
            return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

        with (
            patch.object(project_mod, "MINIONS_ROOT", tmp_path),
            patch.object(project_mod.subprocess, "run", side_effect=fake_run),
        ):
            project_mod._bootstrap_coder_graph(workspace)

        # Give any (incorrectly) spawned daemon thread a moment to fire.
        time.sleep(0.05)
        assert called == [], (
            "bootstrap must not invoke codegraph when .codegraph/ already exists"
        )

    def test_no_op_when_binary_missing(self, tmp_path: Path) -> None:
        """If install.sh has not populated node_modules, no-op."""
        workspace = tmp_path / "branches" / "coder"
        workspace.mkdir(parents=True)
        # Deliberately do not create the cg_bin stub — simulate missing binary.

        called = []

        def fake_run(*args, **kwargs) -> subprocess.CompletedProcess:
            called.append(args)
            return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

        with (
            patch.object(project_mod, "MINIONS_ROOT", tmp_path),
            patch.object(project_mod.subprocess, "run", side_effect=fake_run),
        ):
            project_mod._bootstrap_coder_graph(workspace)

        time.sleep(0.05)
        assert called == [], "bootstrap must not invoke codegraph when binary is missing"

    def test_failing_init_writes_error_marker(self, tmp_path: Path) -> None:
        """A non-zero exit must drop a `.codegraph-bootstrap.error` file.

        The marker is the operator-facing surface — `mos doctor` and
        `mos status` can scan for it; without the marker, a silent
        bootstrap failure goes unnoticed until Coder's first
        codegraph_search call returns "index missing".
        """
        workspace = tmp_path / "branches" / "coder"
        workspace.mkdir(parents=True)
        _make_fake_cg_bin(tmp_path)

        def failing_run(*args, **kwargs) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(
                args=args[0],
                returncode=2,
                stdout="",
                stderr="boom: parser error on file foo.py",
            )

        with (
            patch.object(project_mod, "MINIONS_ROOT", tmp_path),
            patch.object(project_mod.subprocess, "run", side_effect=failing_run),
            patch.dict(os.environ, {"MINIONS_BOOTSTRAP_CODER_GRAPH_SYNC": "1"}),
        ):
            project_mod._bootstrap_coder_graph(workspace)

        marker = workspace / ".codegraph-bootstrap.error"
        assert marker.is_file(), "expected error marker to exist after failed init"
        text = marker.read_text(encoding="utf-8")
        assert "exit=2" in text
        assert "parser error" in text
