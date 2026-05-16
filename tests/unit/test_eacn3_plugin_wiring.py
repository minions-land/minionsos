"""Pin the EACN3-MCP-plugin wiring invariants.

These assertions guard the "Role ↔ EACN3 over `eacn3_*` tools" path that is
required by the root constitution but is easy to silently lose by editing
``.mcp.json`` or ``install.sh``. Breaking any of them means Roles fall back
to artifact-only communication and Gru stops seeing bus traffic.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class TestMcpConfigMountsEacn3:
    def test_mcp_json_has_both_servers(self) -> None:
        cfg = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
        servers = cfg.get("mcpServers", {})
        assert "minionsos" in servers, "minionsos MCP server missing"
        assert "eacn3" in servers, "eacn3 MCP server missing — Roles will have no eacn3_* tools"

    def test_eacn3_entry_runs_plugin_dist(self) -> None:
        cfg = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
        eacn3 = cfg["mcpServers"]["eacn3"]
        assert eacn3["command"] == "node"
        args = eacn3["args"]
        assert any("EACN3/plugin/dist/server.js" in a for a in args), args


class TestCodexMcpConfigMountsEacn3:
    def test_codex_config_has_both_servers(self) -> None:
        import tomllib

        cfg = tomllib.loads((ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"))
        servers = cfg.get("mcp_servers", {})
        assert "minionsos" in servers, "minionsos MCP server missing from Codex config"
        assert "eacn3" in servers, "eacn3 MCP server missing from Codex config"

    def test_codex_eacn3_entry_runs_plugin_direct(self) -> None:
        """Codex MCP points at the EACN3 plugin directly — no MinionsOS proxy."""
        import tomllib

        cfg = tomllib.loads((ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"))
        eacn3 = cfg["mcp_servers"]["eacn3"]
        assert eacn3["command"] == "node"
        args = eacn3["args"]
        assert any("EACN3/plugin/dist/server.js" in a for a in args), args


class TestInstallShMandatoryPluginBuild:
    def test_install_fails_without_node(self) -> None:
        text = (ROOT / "install.sh").read_text(encoding="utf-8")
        assert "MINIONS_SKIP_PLUGIN_BUILD" in text
        assert "skipping EACN3 plugin build" not in text or "MINIONS_SKIP_PLUGIN_BUILD" in text
        assert "dist/server.js" in text


class TestDoctorEacn3Checks:
    def test_doctor_has_plugin_and_node_and_mcp_checks(self) -> None:
        text = (ROOT / "minions" / "cli.py").read_text(encoding="utf-8")
        for name in (
            "eacn3-plugin-built",
            "node>=16",
            "mcp-config-mounts-eacn3",
            "codex-mcp-config-mounts-eacn3",
            "codex-mcp-eacn3-direct",
        ):
            assert name in text, f"doctor lost check: {name}"
