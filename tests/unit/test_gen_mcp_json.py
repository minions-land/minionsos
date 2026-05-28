"""Tests for the .mcp.json generator (Issue #27 absolute-path fix)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_generated_mcp_json_uses_absolute_paths(tmp_path: Path) -> None:
    """Issue #27: every command/args path must be absolute.

    Role processes run with cwd=branches/<role>/ — relative paths in
    .mcp.json fail to resolve and the MCP server silently drops, leaving
    the role with no eacn3_* tools.
    """
    # Build a minimal fake MinionsOS-shaped layout under tmp_path so the
    # generator's `codex_dist.is_file()` branch is exercised either way.
    fake_root = tmp_path / "MinionsOS"
    (fake_root / "mcp-servers" / "eacn3" / "plugin" / "dist").mkdir(parents=True)
    (fake_root / "mcp-servers" / "keepalive").mkdir(parents=True)
    (fake_root / "mcp-servers" / "eacn3" / "plugin" / "dist" / "server.js").write_text("// stub")
    (fake_root / "mcp-servers" / "keepalive" / "server.py").write_text("# stub")

    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "minions" / "tools" / "_gen_mcp_json.py"),
            str(fake_root),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    out_path = fake_root / ".mcp.json"
    assert out_path.is_file()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    servers = data["mcpServers"]

    expected = {"minionsos", "eacn3", "keepalive"}
    assert expected.issubset(set(servers.keys()))

    # No relative paths in any command/args.
    for name, spec in servers.items():
        for arg in spec["args"]:
            assert not arg.startswith("mcp-servers/"), (
                f"{name} server has relative arg {arg!r}; "
                "must be absolute or roles will fail to load it"
            )
            # Filesystem paths look like absolute paths starting with /.
            if "/" in arg and not arg.startswith("-"):
                # Must be absolute or a flag like '--project'
                assert arg.startswith("/") or arg.startswith("--"), (
                    f"{name} arg {arg!r} appears to be a non-absolute filesystem path"
                )

    # Sanity: eacn3's server.js arg must point at our fake file.
    eacn3_args = servers["eacn3"]["args"]
    expected_eacn3 = fake_root / "mcp-servers" / "eacn3" / "plugin" / "dist" / "server.js"
    assert eacn3_args[0] == str(expected_eacn3)
    assert Path(eacn3_args[0]).is_file()

    # Sanity: minionsos uses absolute --project path.
    minionsos_args = servers["minionsos"]["args"]
    assert "--project" in minionsos_args
    project_idx = minionsos_args.index("--project") + 1
    assert minionsos_args[project_idx] == str(fake_root)


def test_generated_mcp_json_eacn3_present_for_role_cwd(tmp_path: Path) -> None:
    """The original Issue #27 symptom: a role process running from
    branches/<role>/ couldn't see eacn3_* tools. Verify the new
    generator's absolute path resolves the same regardless of cwd."""
    fake_root = tmp_path / "MinionsOS"
    eacn3_path = fake_root / "mcp-servers" / "eacn3" / "plugin" / "dist"
    eacn3_path.mkdir(parents=True)
    (eacn3_path / "server.js").write_text("// stub")
    (fake_root / "mcp-servers" / "keepalive").mkdir(parents=True)
    (fake_root / "mcp-servers" / "keepalive" / "server.py").write_text("")

    repo_root = Path(__file__).resolve().parents[2]
    subprocess.run(
        [
            sys.executable,
            str(repo_root / "minions" / "tools" / "_gen_mcp_json.py"),
            str(fake_root),
        ],
        check=True,
    )
    data = json.loads((fake_root / ".mcp.json").read_text(encoding="utf-8"))

    # Simulate a role-cwd: the absolute path must still resolve to the file.
    role_cwd = fake_root / "branches" / "coder"
    role_cwd.mkdir(parents=True)
    eacn3_arg = Path(data["mcpServers"]["eacn3"]["args"][0])
    assert eacn3_arg.is_absolute()
    assert eacn3_arg.is_file(), (
        f"absolute eacn3 server path {eacn3_arg} does not exist; "
        f"node would fail to start it from cwd={role_cwd}"
    )


def test_generated_codex_config_uses_absolute_paths(tmp_path: Path) -> None:
    """Issue #27 mirror: .codex/config.toml had the same relative-path bug.

    Codex spawns its MCP children from whichever cwd it was launched in
    (typically branches/<role>/), so any relative path in
    config.toml fails to resolve.
    """
    fake_root = tmp_path / "MinionsOS"
    eacn3_path = fake_root / "mcp-servers" / "eacn3" / "plugin" / "dist"
    eacn3_path.mkdir(parents=True)
    (eacn3_path / "server.js").write_text("// stub")
    (fake_root / "mcp-servers" / "keepalive").mkdir(parents=True)
    (fake_root / "mcp-servers" / "keepalive" / "server.py").write_text("")

    repo_root = Path(__file__).resolve().parents[2]
    out = fake_root / ".codex" / "config.toml"
    subprocess.run(
        [
            sys.executable,
            str(repo_root / "minions" / "tools" / "_gen_codex_config.py"),
            str(out),
            str(fake_root),
        ],
        check=True,
    )
    text = out.read_text(encoding="utf-8")

    # No bare relative `mcp-servers/...` paths anywhere.
    assert '"mcp-servers/' not in text, (
        "codex config still contains relative mcp-servers/* paths"
    )
    # Sanity: eacn3 plugin path is the absolute one we set up.
    assert str(fake_root / "mcp-servers" / "eacn3" / "plugin" / "dist" / "server.js") in text
    # The generator preserves the list_roles approval gate.
    assert "[mcp_servers.minionsos.tools.list_roles]" in text
    assert 'approval_mode = "approve"' in text
    # The descriptive comment block is preserved.
    assert "EACN3 plugin is mounted directly" in text
