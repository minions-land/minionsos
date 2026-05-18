"""Unit tests for the scaffold + audit surface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minions.scaffold import audit as audit_module
from minions.scaffold import contracts, generators

# ---------------------------------------------------------------------------
# Fixture: a fully-isolated fake repo wired into contracts.* paths.
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "fake-repo"
    package = repo / "minions"
    for sub in ("roles", "review/templates", "review/skills", "domains", "tools"):
        (package / sub).mkdir(parents=True, exist_ok=True)
    (repo / "mcp-servers").mkdir()

    monkeypatch.setattr(contracts, "REPO_ROOT", repo)
    monkeypatch.setattr(contracts, "PACKAGE_ROOT", package)
    monkeypatch.setattr(contracts, "ROLES_DIR", package / "roles")
    monkeypatch.setattr(contracts, "REVIEW_DIR", package / "review")
    monkeypatch.setattr(contracts, "DOMAINS_DIR", package / "domains")
    monkeypatch.setattr(contracts, "TOOLS_DIR", package / "tools")
    monkeypatch.setattr(contracts, "MCP_SERVERS_DIR", repo / "mcp-servers")
    monkeypatch.setattr(contracts, "MCP_JSON", repo / ".mcp.json")
    monkeypatch.setattr(contracts, "ROOT_CLAUDE_MD", repo / "CLAUDE.md")
    monkeypatch.setattr(contracts, "PACKAGE_CLAUDE_MD", package / "CLAUDE.md")

    monkeypatch.setattr(generators, "ROLES_DIR", package / "roles")
    monkeypatch.setattr(generators, "REVIEW_DIR", package / "review")
    monkeypatch.setattr(generators, "DOMAINS_DIR", package / "domains")
    monkeypatch.setattr(generators, "TOOLS_DIR", package / "tools")
    return repo


def _seed_role(repo: Path, name: str, *, system_md: bool = True) -> None:
    role_dir = repo / "minions" / "roles" / name
    role_dir.mkdir(parents=True, exist_ok=True)
    if system_md:
        (role_dir / "SYSTEM.md").write_text(f"# {name}\n", encoding="utf-8")


def _seed_minimal_repo(repo: Path) -> None:
    """Seed CLAUDE.md, .mcp.json, README so structural checks have a baseline."""
    (repo / "CLAUDE.md").write_text(
        "| Gru main | a | b | c | d | e | f |\n"
        "| Coder main | a | b | c | d | e | f |\n"
        "| Noter main | a | b | c | d | e | f |\n"
        "| Writer main | a | b | c | d | e | f |\n"
        "| Ethics main | a | b | c | d | e | f |\n"
        "| Expert main | a | b | c | d | e | f |\n",
        encoding="utf-8",
    )
    (repo / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "minionsos": {"type": "stdio", "command": "uv", "args": []},
                }
            }
        ),
        encoding="utf-8",
    )
    (repo / "mcp-servers" / "README.md").write_text("# MCP Servers\n", encoding="utf-8")
    for role in ("gru", "coder", "noter", "writer", "ethics", "expert"):
        _seed_role(repo, role)


# ---------------------------------------------------------------------------
# Generator tests
# ---------------------------------------------------------------------------


def test_generate_role_writes_system_md_and_skills_dir(fake_repo: Path) -> None:
    result = generators.generate_role("librarian", title="Librarian")
    sys_md = fake_repo / "minions" / "roles" / "librarian" / "SYSTEM.md"
    assert sys_md.is_file()
    assert "# Librarian — System Prompt" in sys_md.read_text(encoding="utf-8")
    assert (fake_repo / "minions" / "roles" / "librarian" / "skills").is_dir()
    assert "FIXED_ROLES" in " ".join(result.manual_followups)


def test_generate_role_skill_requires_existing_role(fake_repo: Path) -> None:
    with pytest.raises(generators.ScaffoldError):
        generators.generate_role_skill("ghost", "evidence-audit")


def test_generate_role_skill_writes_frontmatter_and_summary(fake_repo: Path) -> None:
    _seed_role(fake_repo, "coder")
    result = generators.generate_role_skill(
        "coder", "evidence-audit", summary="Audit evidence chain"
    )
    body = result.paths_written[0].read_text(encoding="utf-8")
    assert body.startswith("---\nslug: evidence-audit\n")
    assert "summary: Audit evidence chain" in body


def test_generate_review_template(fake_repo: Path) -> None:
    result = generators.generate_review_template("rebuttal-note", title="Rebuttal Note")
    body = result.paths_written[0].read_text(encoding="utf-8")
    assert body.startswith("# Rebuttal Note")


def test_generate_domain(fake_repo: Path) -> None:
    result = generators.generate_domain("rl-theory", title="RL Theory")
    body = result.paths_written[0].read_text(encoding="utf-8")
    assert "Domain Pack: RL Theory (rl-theory)" in body


def test_generate_mcp_tool_rejects_non_mos_prefix(fake_repo: Path) -> None:
    with pytest.raises(generators.ScaffoldError):
        generators.generate_mcp_tool("frob_widget")


def test_generate_mcp_tool_emits_args_class(fake_repo: Path) -> None:
    result = generators.generate_mcp_tool("mos_widget_kick")
    body = result.paths_written[0].read_text(encoding="utf-8")
    assert "class MosWidgetKickArgs(BaseModel):" in body


def test_generate_refuses_to_overwrite_without_force(fake_repo: Path) -> None:
    generators.generate_domain("rl-theory")
    with pytest.raises(generators.ScaffoldError):
        generators.generate_domain("rl-theory")
    generators.generate_domain("rl-theory", force=True)


# ---------------------------------------------------------------------------
# Audit tests
# ---------------------------------------------------------------------------


def test_audit_clean_baseline_has_no_errors(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_minimal_repo(fake_repo)
    monkeypatch.setattr(contracts, "fixed_roles", lambda: {"coder", "noter", "writer", "ethics"})
    issues = audit_module.audit()
    errors = [i for i in issues if i.severity == "error"]
    assert errors == [], errors


def test_audit_flags_role_dir_missing_system_md(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_minimal_repo(fake_repo)
    monkeypatch.setattr(contracts, "fixed_roles", lambda: set())
    _seed_role(fake_repo, "broken", system_md=False)
    surfaces = {i.surface for i in audit_module.check_role_dirs_have_system_md()}
    assert "roles" in surfaces


def test_audit_flags_fixed_role_without_dir(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_minimal_repo(fake_repo)
    monkeypatch.setattr(contracts, "fixed_roles", lambda: {"phantom"})
    issues = audit_module.check_fixed_roles_have_dir()
    assert any("phantom" in i.message for i in issues)


def test_audit_flags_unregistered_mcp_server_dir(fake_repo: Path) -> None:
    _seed_minimal_repo(fake_repo)
    (fake_repo / "mcp-servers" / "drifting").mkdir()
    issues = audit_module.check_mcp_servers_registered()
    assert any("drifting" in i.message for i in issues)


def test_audit_flags_orphan_mcp_tool(fake_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server = fake_repo / "minions" / "tools" / "mcp_server.py"
    server.write_text(
        "@mcp.tool()\ndef mos_orphan_tool(args):\n    return {}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        contracts,
        "whitelist_table",
        lambda: {("coder", "main"): ["Read"]},
    )
    issues = audit_module.check_mcp_tools_whitelisted()
    assert any("mos_orphan_tool" in i.message for i in issues)


def test_audit_wildcard_match_passes(fake_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server = fake_repo / "minions" / "tools" / "mcp_server.py"
    server.write_text(
        "@mcp.tool()\ndef mos_dag_append(args):\n    return {}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        contracts,
        "whitelist_table",
        lambda: {("noter", "main"): ["mos_dag_*"]},
    )
    issues = audit_module.check_mcp_tools_whitelisted()
    assert issues == []


# ---------------------------------------------------------------------------
# New audit checks (S2, S3, S5, P1, P2 from red-team review)
# ---------------------------------------------------------------------------


def test_check_whitelist_entries_resolve_flags_dead_entry(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = fake_repo / "minions" / "tools" / "mcp_server.py"
    server.write_text("@mcp.tool()\ndef mos_real_tool(args):\n    return {}\n", encoding="utf-8")
    monkeypatch.setattr(
        contracts,
        "whitelist_table",
        lambda: {("coder", "main"): ["mos_real_tool", "mos_quantum_teleport"]},
    )
    issues = audit_module.check_whitelist_entries_resolve()
    assert any("mos_quantum_teleport" in i.message for i in issues)
    assert not any("mos_real_tool" in i.message for i in issues)


def test_check_whitelist_entries_resolve_accepts_wildcard(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = fake_repo / "minions" / "tools" / "mcp_server.py"
    server.write_text("@mcp.tool()\ndef mos_dag_append(args):\n    return {}\n", encoding="utf-8")
    monkeypatch.setattr(
        contracts,
        "whitelist_table",
        lambda: {("noter", "main"): ["mos_dag_*"]},
    )
    assert audit_module.check_whitelist_entries_resolve() == []


def test_check_publish_policy_matches_boundaries_flags_extra_subdir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        contracts,
        "role_publish_policy",
        lambda: {"noter": {"notes", "exploration", "handoffs", "exp"}},
    )
    monkeypatch.setattr(
        contracts,
        "role_write_boundaries",
        lambda: {
            "noter": [
                "branches/noter/",
                "branches/shared/notes/",
                "branches/shared/exploration/",
                "branches/shared/handoffs/",
            ]
        },
    )
    issues = audit_module.check_publish_policy_matches_boundaries()
    assert any(
        "exp" in i.message and "ROLE_WRITE_BOUNDARIES does not list" in i.message for i in issues
    )


def test_check_subagent_not_broader_than_main_flags_drift(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        contracts,
        "whitelist_table",
        lambda: {
            ("librarian", "main"): ["Read"],
            ("librarian", "subagent"): ["Read", "Write", "Edit"],
        },
    )
    monkeypatch.setattr(contracts, "list_registered_mcp_tools", lambda: [])
    issues = audit_module.check_subagent_not_broader_than_main()
    assert any(
        "librarian" in i.message and "Write" in i.message and "Edit" in i.message for i in issues
    )


def test_check_subagent_not_broader_when_aligned(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        contracts,
        "whitelist_table",
        lambda: {
            ("coder", "main"): ["Bash", "Read", "Write"],
            ("coder", "subagent"): ["Read", "Write"],
        },
    )
    monkeypatch.setattr(contracts, "list_registered_mcp_tools", lambda: [])
    assert audit_module.check_subagent_not_broader_than_main() == []


def test_check_codex_on_restricted_role_flags_ethics_pattern(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        contracts,
        "whitelist_table",
        lambda: {("librarian", "main"): ["codex", "Read"]},
    )
    issues = audit_module.check_codex_on_restricted_role()
    assert any("librarian" in i.message and "codex" in i.message for i in issues)


def test_check_codex_silent_when_role_already_has_exec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        contracts,
        "whitelist_table",
        lambda: {("coder", "main"): ["codex", "Bash", "Read", "Write"]},
    )
    assert audit_module.check_codex_on_restricted_role() == []


def test_check_wildcard_baseline_drift(fake_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = fake_repo / "minions" / "scaffold" / "_wildcard_baseline.txt"
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text("mos_dag_*=2\n", encoding="utf-8")
    monkeypatch.setattr(audit_module, "_KNOWN_WILDCARD_TOOL_COUNTS_PATH", baseline)
    server = fake_repo / "minions" / "tools" / "mcp_server.py"
    server.write_text(
        "@mcp.tool()\ndef mos_dag_append(args):\n    return {}\n"
        "@mcp.tool()\ndef mos_dag_query(args):\n    return {}\n"
        "@mcp.tool()\ndef mos_dag_nuke_all(args):\n    return {}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        contracts,
        "whitelist_table",
        lambda: {("gru", "main"): ["mos_dag_*"]},
    )
    issues = audit_module.check_wildcard_tool_set_unchanged()
    assert any("baseline 2" in i.message and "matches 3" in i.message for i in issues)


# ---------------------------------------------------------------------------
# Server-side identity + cross-project checks
# ---------------------------------------------------------------------------


def test_enforce_caller_identity_rejects_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    from minions.tools import mcp_server

    monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")
    monkeypatch.delenv("MINIONS_DISABLE_MCP_AUTHZ", raising=False)
    with pytest.raises(PermissionError, match="role identity mismatch"):
        mcp_server._enforce_caller_identity("gru")


def test_enforce_caller_identity_accepts_match(monkeypatch: pytest.MonkeyPatch) -> None:
    from minions.tools import mcp_server

    monkeypatch.setenv("MINIONS_ROLE_NAME", "coder")
    monkeypatch.delenv("MINIONS_DISABLE_MCP_AUTHZ", raising=False)
    mcp_server._enforce_caller_identity("coder")


def test_enforce_caller_identity_normalises_expert(monkeypatch: pytest.MonkeyPatch) -> None:
    from minions.tools import mcp_server

    monkeypatch.setenv("MINIONS_ROLE_NAME", "expert-rl-theory")
    monkeypatch.delenv("MINIONS_DISABLE_MCP_AUTHZ", raising=False)
    mcp_server._enforce_caller_identity("expert")
    mcp_server._enforce_caller_identity("expert-rl-theory")


def test_enforce_caller_project_rejects_cross_port(monkeypatch: pytest.MonkeyPatch) -> None:
    from minions.tools import mcp_server

    monkeypatch.setenv("MINIONS_PROJECT_PORT", "37596")
    monkeypatch.delenv("MINIONS_DISABLE_MCP_AUTHZ", raising=False)
    with pytest.raises(PermissionError, match="cross-project publish blocked"):
        mcp_server._enforce_caller_project(99999)


def test_enforce_caller_project_accepts_same(monkeypatch: pytest.MonkeyPatch) -> None:
    from minions.tools import mcp_server

    monkeypatch.setenv("MINIONS_PROJECT_PORT", "37596")
    monkeypatch.delenv("MINIONS_DISABLE_MCP_AUTHZ", raising=False)
    mcp_server._enforce_caller_project(37596)


def test_expert_normalisation_no_longer_matches_expertise() -> None:
    from minions.config import resolve_whitelist

    # 'expertise' must NOT inherit expert's full whitelist anymore.
    assert resolve_whitelist("expertise", "main") == []
    # 'expert-rl-theory' continues to inherit the expert whitelist.
    assert resolve_whitelist("expert-rl-theory", "main") == resolve_whitelist("expert", "main")
