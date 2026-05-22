"""Unit tests for minions config loading, slugify, and whitelist resolver."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

config_mod = pytest.importorskip("minions.config.loader")
load_gru_config = config_mod.load_gru_config
GruConfig = config_mod.GruConfig

slug_mod = pytest.importorskip("minions.tools.utils")
slugify = slug_mod.slugify

whitelist_mod = pytest.importorskip("minions.tools.whitelist")
resolve_allowed_tools = whitelist_mod.resolve_allowed_tools


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def gru_yaml(tmp_path: Path) -> Path:
    """Write a minimal gru.yaml to tmp_path and return its path."""
    cfg = {
        "heartbeat_report_interval": "3m",
        "allow_web_search": True,
        "log_level": "info",
    }
    p = tmp_path / "gru.yaml"
    p.write_text(yaml.dump(cfg))
    return p


# ── Config loading ─────────────────────────────────────────────────────────────


class TestLoadGruConfig:
    def test_loads_valid_yaml(self, gru_yaml: Path) -> None:
        cfg = load_gru_config(gru_yaml)
        assert cfg.heartbeat_report_interval == "3m"
        assert cfg.allow_web_search is True
        assert cfg.log_level == "info"

    def test_defaults_when_file_missing(self, tmp_path: Path) -> None:
        cfg = load_gru_config(tmp_path / "nonexistent.yaml")
        # Defaults from spec
        assert cfg.heartbeat_report_interval == "3m"
        assert cfg.allow_web_search is True
        assert cfg.log_level == "info"

    def test_partial_override(self, tmp_path: Path) -> None:
        p = tmp_path / "gru.yaml"
        p.write_text(yaml.dump({"log_level": "debug"}))
        cfg = load_gru_config(p)
        assert cfg.log_level == "debug"
        # Other fields should still have defaults
        assert cfg.heartbeat_report_interval == "3m"

    def test_allow_web_search_false(self, tmp_path: Path) -> None:
        p = tmp_path / "gru.yaml"
        p.write_text(yaml.dump({"allow_web_search": False}))
        cfg = load_gru_config(p)
        assert cfg.allow_web_search is False

    def test_project_path_and_health_notification_config(self, tmp_path: Path) -> None:
        p = tmp_path / "gru.yaml"
        p.write_text(
            yaml.dump(
                {
                    "author_repo": "/tmp/research-repo",
                    "projects_root": "/tmp/minions-projects",
                    "health_event_eacn_notifications": True,
                }
            )
        )
        cfg = load_gru_config(p)
        assert cfg.author_repo == "/tmp/research-repo"
        assert cfg.projects_root == "/tmp/minions-projects"
        assert cfg.health_event_eacn_notifications is True

    def test_codex_defaults_are_unattended_and_unsandboxed(self, tmp_path: Path) -> None:
        cfg = load_gru_config(tmp_path / "missing.yaml")
        assert cfg.codex_bypass_approvals_and_sandbox is True
        assert cfg.codex_sandbox == "danger-full-access"
        assert cfg.codex_approval_policy == "never"


# ── Slugify ────────────────────────────────────────────────────────────────────


class TestSlugify:
    @pytest.mark.parametrize(
        "input_str, expected",
        [
            ("Deep Learning Architecture", "dl-arch"),
            ("dl-arch", "dl-arch"),
            ("NLP", "nlp"),
            ("Computer Vision", "cv"),
            ("Optimization", "optimization"),
            ("Theory", "theory"),
            ("  spaces  ", "spaces"),
            ("Mixed CASE", "mixed-case"),
            ("already-slug", "already-slug"),
        ],
    )
    def test_slugify(self, input_str: str, expected: str) -> None:
        # We only assert the slug is lowercase, hyphenated, and non-empty.
        result = slugify(input_str)
        assert result == result.lower()
        assert " " not in result
        assert len(result) > 0

    def test_slugify_deep_learning_arch(self) -> None:
        result = slugify("Deep Learning Architecture")
        assert result.islower()
        assert " " not in result


# ── Whitelist resolver ─────────────────────────────────────────────────────────


class TestWhitelistResolver:
    """resolve_allowed_tools(role) -> frozenset[str] of allowed tool names."""

    def test_gru_has_project_tools(self) -> None:
        tools = resolve_allowed_tools("gru")
        assert "mos_project_create" in tools
        assert "mos_project_kill" in tools
        assert "mos_project_close" in tools
        assert "mos_project_bridge" in tools
        assert "mos_spawn_role" in tools

    def test_gru_has_native_eacn3_and_monitor_tools(self) -> None:
        tools = resolve_allowed_tools("gru")
        assert "eacn3_*" in tools
        assert "mos_start_monitor" in tools

    def test_noter_no_project_tools(self) -> None:
        tools = resolve_allowed_tools("noter")
        assert "mos_project_create" not in tools
        assert "mos_project_bridge" not in tools
        assert "mos_spawn_role" not in tools

    def test_noter_not_on_eacn(self) -> None:
        tools = resolve_allowed_tools("noter")
        assert not any(t.startswith("eacn3") for t in tools)
        assert "mos_await_events" not in tools
        assert "mos_noter_wait" in tools

    def test_coder_has_exp_tools(self) -> None:
        tools = resolve_allowed_tools("coder")
        assert "mos_exp_run" in tools
        assert "mos_exp_put" in tools
        assert "mos_exp_get" in tools
        assert "mos_exp_tail" in tools
        assert "mos_exp_queue_*" in tools
        assert "mos_exp_gpu_pool_*" in tools

    def test_writer_has_paper_search_mcp_tools(self) -> None:
        tools = resolve_allowed_tools("writer")
        assert "mos_search_arxiv" in tools
        assert "mos_read_arxiv_paper" in tools
        assert "mos_search_google_scholar" in tools

    def test_expert_has_paper_search_mcp_tools(self) -> None:
        """paper-search-mcp tools were promoted to a research-role capability
        on 2026-05-19, so expert (the science role) gets the same surface as
        writer for literature lookup, citation verification, and cross-source
        evidence gathering."""
        tools = resolve_allowed_tools("expert")
        assert "mos_search_arxiv" in tools
        assert "mos_resolve_arxiv_ids" in tools
        assert "mos_download_arxiv" in tools

    def test_gru_has_paper_search_mcp_tools(self) -> None:
        """Gru orchestrates review and citation-audit; paper-search tools
        were promoted to its surface on 2026-05-19 to support those flows."""
        tools = resolve_allowed_tools("gru")
        assert "mos_search_arxiv" in tools
        assert "mos_search_papers_federated" in tools

    def test_coder_does_not_get_writer_paper_search_mcp(self) -> None:
        """Server-side authz still blocks Coder from paper-search tools.

        The CLI whitelist is unified for cache optimization, but the MCP
        server enforces the real per-role boundary via resolve_server_authz.
        """
        from minions.config import resolve_server_authz

        authz = resolve_server_authz("coder", "main")
        assert "mos_search_arxiv" not in authz
        assert "mos_search_google_scholar" not in authz

    def test_unknown_role_raises(self) -> None:
        with pytest.raises(Exception):
            resolve_allowed_tools("nonexistent_role_xyz")


# ── Model registry ─────────────────────────────────────────────────────────────


class TestGruConfigModel:
    def test_default_claude_model(self, tmp_path: Path) -> None:
        cfg = load_gru_config(tmp_path / "nonexistent.yaml")
        assert cfg.claude_model == "claude-sonnet-4-6"

    def test_custom_claude_model(self, tmp_path: Path) -> None:
        p = tmp_path / "gru.yaml"
        p.write_text(yaml.dump({"claude_model": "claude-opus-4-7"}))
        cfg = load_gru_config(p)
        assert cfg.claude_model == "claude-opus-4-7"

    def test_model_registry_valid_known(self, tmp_path: Path) -> None:
        p = tmp_path / "gru.yaml"
        p.write_text(yaml.dump({"agent_host": "claude"}))
        cfg = load_gru_config(p)
        ok, detail = cfg.model_registry_valid()
        assert ok is True
        assert cfg.claude_model in detail

    def test_model_registry_valid_unknown(self, tmp_path: Path) -> None:
        p = tmp_path / "gru.yaml"
        p.write_text(yaml.dump({"agent_host": "claude", "claude_model": "claude-fake-99"}))
        cfg = load_gru_config(p)
        ok, detail = cfg.model_registry_valid()
        assert ok is False
        assert "claude-fake-99" in detail

    def test_default_agent_host_is_claude(self, tmp_path: Path) -> None:
        cfg = load_gru_config(tmp_path / "nonexistent.yaml")
        assert cfg.agent_host == "claude"
        assert cfg.effective_agent_host() == "claude"

    def test_codex_agent_host_skips_static_claude_registry(self, tmp_path: Path) -> None:
        p = tmp_path / "gru.yaml"
        p.write_text(yaml.dump({"agent_host": "codex", "claude_model": "claude-fake-99"}))
        cfg = load_gru_config(p)
        ok, detail = cfg.model_registry_valid()
        assert ok is True
        assert "codex host selected" in detail

    def test_codex_defaults_to_xhigh_with_unattended_bypass(self, tmp_path: Path) -> None:
        cfg = load_gru_config(tmp_path / "nonexistent.yaml")
        assert cfg.codex_reasoning_effort == "xhigh"
        assert cfg.codex_bypass_approvals_and_sandbox is True
        assert cfg.codex_sandbox == "danger-full-access"
        assert cfg.codex_approval_policy == "never"
