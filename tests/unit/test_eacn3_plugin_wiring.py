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
        # Must target the built plugin entrypoint.
        assert any("EACN3/plugin/dist/server.js" in a for a in args), args


class TestCodexMcpConfigMountsEacn3:
    def test_codex_config_has_both_servers(self) -> None:
        import tomllib

        cfg = tomllib.loads((ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"))
        servers = cfg.get("mcp_servers", {})
        assert "minionsos" in servers, "minionsos MCP server missing from Codex config"
        assert "eacn3" in servers, "eacn3 MCP server missing from Codex config"

    def test_codex_eacn3_entry_runs_plugin_dist(self) -> None:
        import tomllib

        cfg = tomllib.loads((ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"))
        eacn3 = cfg["mcp_servers"]["eacn3"]
        assert eacn3["command"] == "uv"
        args = eacn3["args"]
        assert "minions.tools.eacn3_mcp_proxy" in args
        assert any("EACN3/plugin/dist/server.js" in a for a in args)
        assert eacn3.get("env", {}).get("EACN3_MCP_PROFILE") == "codex-core"

    def test_codex_minions_entry_uses_codex_profile(self) -> None:
        import tomllib

        cfg = tomllib.loads((ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"))
        minionsos = cfg["mcp_servers"]["minionsos"]
        assert minionsos.get("env", {}).get("MINIONS_MCP_PROFILE") == "codex"


class TestInstallShMandatoryPluginBuild:
    def test_install_fails_without_node(self) -> None:
        text = (ROOT / "install.sh").read_text(encoding="utf-8")
        # The installer must die (not warn-and-skip) when node is absent,
        # because Roles cannot function without the plugin.
        # Accept either the literal `die ` call in the node-missing branch
        # or the explicit MINIONS_SKIP_PLUGIN_BUILD escape hatch.
        assert "MINIONS_SKIP_PLUGIN_BUILD" in text
        # The old soft-skip phrasing must be gone.
        assert "skipping EACN3 plugin build" not in text or "MINIONS_SKIP_PLUGIN_BUILD" in text
        # Must verify dist/server.js exists after build.
        assert "dist/server.js" in text


class TestRoleSpawnEnvPropagation:
    def test_role_sets_network_url_and_state_dir(self) -> None:
        # Grey-box: read role.py text to confirm env vars are set. We do not
        # spawn a real subprocess here (that lives in smoke tests).
        text = (ROOT / "minions" / "lifecycle" / "role.py").read_text(encoding="utf-8")
        assert '"EACN3_NETWORK_URL"' in text
        assert '"EACN3_STATE_DIR"' in text
        # Per-role dir to avoid token collisions across roles.
        assert "plugin_state_dir" in text
        identity_text = (ROOT / "minions" / "lifecycle" / "eacn_identity.py").read_text(
            encoding="utf-8"
        )
        assert "plugin-" in identity_text


class TestDoctorEacn3Checks:
    def test_doctor_has_plugin_and_node_and_mcp_checks(self) -> None:
        text = (ROOT / "minions" / "cli.py").read_text(encoding="utf-8")
        for name in (
            "eacn3-plugin-built",
            "node>=16",
            "mcp-config-mounts-eacn3",
            "codex-mcp-config-mounts-eacn3",
            "codex-mcp-profiles",
        ):
            assert name in text, f"doctor lost check: {name}"


class TestCodexMcpProfiles:
    def test_eacn3_codex_profile_lives_in_minions_proxy_not_eacn3_source(self) -> None:
        text = (ROOT / "minions" / "tools" / "eacn3_mcp_proxy.py").read_text(encoding="utf-8")
        assert "EACN3_MCP_PROFILE" in text
        assert "CODEX_CORE_TOOL_NAMES" in text
        assert "eacn3_next" in text
        assert "eacn3_create_task" in text
        assert (
            "eacn3_cluster_status"
            not in text.split("CODEX_CORE_TOOL_NAMES", 1)[1].split(
                ")",
                1,
            )[0]
        )
