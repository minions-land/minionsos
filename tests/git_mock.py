"""
Universal Git Command Mock for MinionsOS Tests

This module provides a comprehensive mock for git commands to enable
testing without real git operations.
"""

import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def mock_git_operations(monkeypatch):
    """Mock git commands to avoid real git operations in tests.

    This fixture intercepts subprocess.run calls for git commands and
    provides fake successful responses, while allowing non-git commands
    to pass through.
    """
    original_run = subprocess.run

    # Track state
    branches = set()
    worktrees = {}

    def mock_git_run(cmd, *args, **kwargs):
        """Mock git commands"""
        if not isinstance(cmd, list) or len(cmd) < 2 or cmd[0] != "git":
            return original_run(cmd, *args, **kwargs)

        git_cmd = cmd[1]
        cwd = kwargs.get("cwd", ".")

        # git init --bare
        if git_cmd == "init" and "--bare" in cmd:
            target = Path(cmd[-1])
            target.mkdir(parents=True, exist_ok=True)

            # Create basic bare repo structure
            (target / "HEAD").write_text("ref: refs/heads/main\n")
            (target / "refs" / "heads").mkdir(parents=True, exist_ok=True)
            (target / "refs" / "tags").mkdir(parents=True, exist_ok=True)
            (target / "objects").mkdir(parents=True, exist_ok=True)
            (target / "hooks").mkdir(parents=True, exist_ok=True)
            (target / "info").mkdir(parents=True, exist_ok=True)
            (target / "config").write_text("[core]\n\trepositoryformatversion = 0\n\tbare = true\n")

            return Mock(returncode=0, stdout="", stderr="")

        # git worktree add
        if git_cmd == "worktree" and "add" in cmd:
            try:
                b_idx = cmd.index("-b")
                branch = cmd[b_idx + 1]
                path = Path(cmd[b_idx + 2])

                # Remove existing branch if exists
                if branch in branches:
                    branches.remove(branch)

                # Create worktree directory with basic git structure
                path.mkdir(parents=True, exist_ok=True)

                # Create .git file pointing to main repo (worktree format)
                git_dir = Path(cwd) / "worktrees" / branch
                git_dir.mkdir(parents=True, exist_ok=True)
                (path / ".git").write_text(f"gitdir: {git_dir}\n")

                # Create complete git structure in the worktree git dir
                (git_dir / "HEAD").write_text(f"ref: refs/heads/{branch}\n")

                # Handle branch names with slashes (create nested directories)
                branch_ref_path = git_dir / "refs" / "heads" / branch
                branch_ref_path.parent.mkdir(parents=True, exist_ok=True)
                branch_ref_path.write_text("abc123def456789012345678901234567890abcd\n")

                # Create logs directory
                logs_ref_path = git_dir / "logs" / "refs" / "heads" / branch
                logs_ref_path.parent.mkdir(parents=True, exist_ok=True)

                (git_dir / "objects").mkdir(parents=True, exist_ok=True)
                (git_dir / "commondir").write_text("../..\n")

                # Create gitdir file
                (git_dir / "gitdir").write_text(f"{path}/.git\n")

                branches.add(branch)
                worktrees[str(path)] = branch

                return Mock(
                    returncode=0,
                    stdout=f"Preparing worktree (new branch '{branch}')\n",
                    stderr="",
                    check_returncode=lambda: None,
                )
            except (ValueError, IndexError):
                pass

        # git worktree remove
        if git_cmd == "worktree" and "remove" in cmd:
            return Mock(returncode=0, stdout="", stderr="")

        # git branch -D
        if git_cmd == "branch" and "-D" in cmd:
            try:
                branch = cmd[cmd.index("-D") + 1]
                branches.discard(branch)
                return Mock(returncode=0, stdout="", stderr="")
            except (ValueError, IndexError):
                pass

        # git add
        if git_cmd == "add":
            return Mock(returncode=0, stdout="", stderr="")

        # git commit
        if git_cmd == "commit":
            return Mock(
                returncode=0, stdout="[main abc1234] commit message\n 1 file changed\n", stderr=""
            )

        # git config (read/write)
        if git_cmd == "config":
            if "--get" in cmd:
                return Mock(returncode=0, stdout="value\n", stderr="")
            else:
                return Mock(returncode=0, stdout="", stderr="")

        # git rev-parse (important - needs real execution or fake sha)
        if git_cmd == "rev-parse":
            if "HEAD" in cmd:
                # Return a fake SHA
                return Mock(
                    returncode=0, stdout="abc123def456789012345678901234567890abcd\n", stderr=""
                )
            # Other rev-parse commands pass through
            return original_run(cmd, *args, **kwargs)

        # git archive (need to handle specially)
        if git_cmd == "archive":
            # Return empty tar stream
            import io

            return Mock(returncode=0, stdout=io.BytesIO(b""), stderr="")

        # git push
        if git_cmd == "push":
            return Mock(returncode=0, stdout="", stderr="")

        # git remote
        if git_cmd == "remote":
            return Mock(returncode=0, stdout="", stderr="")

        # Default: pass through for real git operations (like git init in fixtures)
        return original_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", mock_git_run)

    # Also mock Popen for archive operations
    original_popen = subprocess.Popen

    def mock_git_popen(cmd, *args, **kwargs):
        if isinstance(cmd, list) and len(cmd) >= 2 and cmd[0] == "git" and cmd[1] == "archive":
            # Create a real pipe for stdout
            import os

            r, w = os.pipe()
            # Write empty tar to the pipe and close write end
            os.write(w, b"")
            os.close(w)

            mock_proc = Mock()
            mock_proc.stdout = os.fdopen(r, "rb")
            mock_proc.stderr = Mock()
            mock_proc.stderr.read = lambda: b""
            mock_proc.returncode = 0
            mock_proc.wait = lambda: 0
            mock_proc.communicate = lambda: (b"", b"")
            mock_proc.poll = lambda: 0
            return mock_proc
        return original_popen(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", mock_git_popen)

    yield
