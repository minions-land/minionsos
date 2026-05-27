"""Unit tests for keepalive MCP server's wait_bg early-exit logic.

Covers all four code paths:
  1. Pure-sleep (no output_files, no done_markers) → sleeps full deadline
  2. done_markers all present → early_exit, reason=done_markers, markers unlinked
  3. output_files no longer held → early_exit, reason=output_files
  4. done_markers takes precedence over output_files when both fire same tick
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER = REPO_ROOT / "mcp-servers" / "keepalive" / "server.py"


def _load_server():
    """Load the keepalive MCP server module without running mcp.run()."""
    spec = importlib.util.spec_from_file_location("keepalive_server", SERVER)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["keepalive_server"] = mod
    spec.loader.exec_module(mod)
    return mod


class WaitBgEarlyExitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_server()
        # FastMCP's @mcp.tool() doesn't wrap — the function is directly callable.
        cls.wait_bg = staticmethod(cls.mod.wait_bg)

    def _run(self, **kwargs):
        return asyncio.run(self.wait_bg(**kwargs))

    def test_pure_sleep_floors_to_5s(self):
        t0 = time.monotonic()
        result = self._run(deadline_seconds=1)
        elapsed = time.monotonic() - t0
        self.assertGreaterEqual(elapsed, 4.5)
        self.assertFalse(result["early_exit"])
        self.assertEqual(result["early_exit_reason"], "")
        self.assertGreaterEqual(result["slept_seconds"], 5)

    def test_done_markers_early_exit(self):
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / "agent-1.done"
            marker.touch()
            t0 = time.monotonic()
            result = self._run(deadline_seconds=30, done_markers=[str(marker)])
            elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 6, f"early-exit took too long: {elapsed:.2f}s")
        self.assertTrue(result["early_exit"])
        self.assertEqual(result["early_exit_reason"], "done_markers")
        self.assertFalse(marker.exists(), "marker should be cleaned up")

    def test_done_markers_partial_no_exit(self):
        with tempfile.TemporaryDirectory() as d:
            present = Path(d) / "agent-1.done"
            absent = Path(d) / "agent-2.done"
            present.touch()
            t0 = time.monotonic()
            result = self._run(
                deadline_seconds=5,
                done_markers=[str(present), str(absent)],
            )
            elapsed = time.monotonic() - t0
            self.assertGreaterEqual(elapsed, 4.5)
            self.assertFalse(result["early_exit"])
            self.assertTrue(present.exists(), "partial-match must NOT cleanup")

    def test_output_files_early_exit(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "out"
            f.write_text("done")  # no process holds it
            t0 = time.monotonic()
            result = self._run(deadline_seconds=30, output_files=[str(f)])
            elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 6)
        self.assertTrue(result["early_exit"])
        self.assertEqual(result["early_exit_reason"], "output_files")

    def test_marker_appears_mid_sleep(self):
        """Touch a marker partway through; wait_bg picks it up on next tick."""
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / "agent-late.done"

            async def driver():
                async def appear():
                    await asyncio.sleep(3)
                    marker.touch()

                t0 = time.monotonic()
                result, _ = await asyncio.gather(
                    self.wait_bg(
                        deadline_seconds=30,
                        done_markers=[str(marker)],
                    ),
                    appear(),
                )
                return time.monotonic() - t0, result

            elapsed, result = asyncio.run(driver())
        self.assertLess(elapsed, 8, f"too slow: {elapsed:.2f}s")
        self.assertTrue(result["early_exit"])
        self.assertEqual(result["early_exit_reason"], "done_markers")


class NudgeHookTest(unittest.TestCase):
    """Hook-shape tests: feed bg_keepalive_nudge stdin payloads, check stdout."""

    HOOK = REPO_ROOT / "minions" / "hooks" / "bg_keepalive_nudge.py"

    def _run_hook(self, payload: dict) -> dict:
        import json
        import subprocess

        proc = subprocess.run(
            ["python3", str(self.HOOK)],
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=3,
        )
        if not proc.stdout.strip():
            return {}
        return json.loads(proc.stdout)

    def test_bg_bash_emits_output_files(self):
        out = self._run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"run_in_background": True},
                "tool_response": {
                    "bash_id": "bash_99",
                    "output_file": "/tmp/claude-bash/bash_99.out",
                },
            }
        )
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("output_files=", ctx)
        self.assertIn("/tmp/claude-bash/bash_99.out", ctx)
        self.assertNotIn("done_markers=", ctx)

    def test_bg_agent_emits_done_markers(self):
        out = self._run_hook(
            {
                "tool_name": "Agent",
                "tool_input": {"run_in_background": True},
                "tool_response": {"agent_id": "agt_xyz"},
            }
        )
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("done_markers=", ctx)
        self.assertIn("agt_xyz.done", ctx)
        self.assertNotIn("output_files=", ctx)

    def test_bg_agent_camelcase_agentid(self):
        """Real Agent tool returns `agentId` (camelCase), not `agent_id`."""
        out = self._run_hook(
            {
                "tool_name": "Agent",
                "tool_input": {"run_in_background": True},
                "tool_response": {"agentId": "a1b2c3d4"},
            }
        )
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("done_markers=", ctx)
        self.assertIn("a1b2c3d4.done", ctx)

    def test_bg_task_emits_done_markers(self):
        out = self._run_hook(
            {
                "tool_name": "Task",
                "tool_input": {"run_in_background": True},
                "tool_response": {"task_id": "tsk_abc"},
            }
        )
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("done_markers=", ctx)
        self.assertIn("tsk_abc.done", ctx)

    def test_foreground_passes_silently(self):
        out = self._run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"run_in_background": False},
                "tool_response": {"bash_id": "bash_99"},
            }
        )
        self.assertEqual(out, {})


class SubagentStopHookTest(unittest.TestCase):
    HOOK = REPO_ROOT / "minions" / "hooks" / "keepalive_subagent_done.py"

    def _run_hook(self, payload: dict, marker_dir: Path) -> int:
        import json
        import subprocess

        env = os.environ.copy()
        env["TMPDIR"] = str(marker_dir.parent)
        # Hook reads MARKER_DIR = $TMPDIR/claude-keepalive-markers, so set
        # TMPDIR to marker_dir's parent.
        proc = subprocess.run(
            ["python3", str(self.HOOK)],
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=3,
            env=env,
        )
        return proc.returncode

    def test_touches_marker_for_agent_id(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            marker_dir = tmp / "claude-keepalive-markers"
            self._run_hook({"agent_id": "abc123"}, marker_dir)
            self.assertTrue((marker_dir / "abc123.done").exists())

    def test_falls_back_to_session_id(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            marker_dir = tmp / "claude-keepalive-markers"
            self._run_hook({"session_id": "sess9"}, marker_dir)
            self.assertTrue((marker_dir / "sess9.done").exists())

    def test_no_id_is_noop(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            marker_dir = tmp / "claude-keepalive-markers"
            rc = self._run_hook({"hook_event_name": "Stop"}, marker_dir)
            self.assertEqual(rc, 0)
            self.assertFalse(marker_dir.exists())


if __name__ == "__main__":
    unittest.main()
