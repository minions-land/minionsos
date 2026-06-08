"""Project creation implementation.

Implements the full project_create flow: allocating ports, seeding git repos,
starting backends, registering agents, and bootstrapping roles.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from minions.config import load_gru_config, slugify
from minions.errors import BackendError, ProjectError
from minions.lifecycle import _project_templates
from minions.lifecycle.eacn_identity import identity_map_for_meta
from minions.lifecycle.project_backend import (
    register_gru_eacn_agent,
    register_server,
    start_backend,
    wait_for_health,
)
from minions.lifecycle.project_paths import (
    ensure_workspace_layout,
    seed_per_project_repo,
    write_project_gitignore,
)
from minions.lifecycle.project_worktree import (
    create_shared_worktree,
    create_worktree,
)
from minions.paths import (
    project_dir,
    project_logs_dir,
    project_main_workspace,
    project_meta_json,
    project_shared_draft_json,
)
from minions.state.store import ProjectEntry, StateStore

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _prepare_project_tree(port: int, base_branch: str) -> tuple[str, Path]:
    """Create the project directory, bare repo, and main worktree for *port*."""
    pdir = project_dir(port)
    pdir.mkdir(parents=True, exist_ok=True)
    ensure_workspace_layout(port)
    project_logs_dir(port).mkdir(parents=True, exist_ok=True)
    (pdir / "eacn3_data").mkdir(parents=True, exist_ok=True)
    write_project_gitignore(pdir)

    try:
        seed_per_project_repo(port)
        branch = create_worktree(port, base_branch)
        create_shared_worktree(port)  # no-op shim; shared surface is on main
    except ProjectError as exc:
        logger.error("Worktree creation failed: %s", exc)
        raise
    return branch, pdir


def seed_draft_bootstrap(
    port: int,
    profile_name: str,
    mission_profile: Any,
    real_name: str,
    brief: str | None,
    topic_doc: str | None,
) -> None:
    """Seed the Draft with a bootstrap node (B-000) as the project root.

    The bootstrap node serves as:
    - The cold-start trigger for Roles (they read it on first wake)
    - The L1 memory root (all subsequent nodes derive from this context)
    - A durable record of the project's initial state

    Written to branches/shared/draft/draft.json immediately after
    shared worktree creation, before any Role spawns.
    """
    draft_path = project_shared_draft_json(port)
    draft_path.parent.mkdir(parents=True, exist_ok=True)

    bootstrap_text = brief or f"Project: {real_name}"
    if topic_doc:
        bootstrap_text += f"\n\nTopic document: {topic_doc}"

    bootstrap_node = {
        "id": "B-000",
        "type": "bootstrap",
        "text": bootstrap_text,
        "support_status": "verified",
        "author_role": "system",
        "created_at": _now_iso(),
        "evidence_tag": "",
        "provenance": "system",
        "confidence": 1.0,
        "metadata": {
            "profile": profile_name,
            "roles_expected": list(mission_profile.roles_active),
            "deliverable": mission_profile.deliverable_schema.get("required", []),
            "topic_doc": topic_doc or "",
            "real_name": real_name,
        },
    }

    draft = {
        "project_port": port,
        "root_question": bootstrap_text,
        "nodes": [bootstrap_node],
        "edges": [],
    }

    tmp = draft_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, draft_path)
    logger.info("Seeded Draft bootstrap node B-000 for port %d", port)


def bootstrap_fixed_roles(
    port: int,
    mission_profile: object,
    store: StateStore,
) -> list[tuple[str, str]]:
    """Spawn the profile-active fixed roles in parallel.

    Without this, all fixed roles wait for the live Gru process to issue
    a serial sequence of mos_spawn_role MCP calls — each call is one
    Opus 4.7 max-effort turn (~60-90s), so the default scientific-paper
    team can take several minutes to come online after project_create
    returns. Pre-spawning in parallel collapses that to a single ~30-60s
    wave; the only real serialization is the file-lock on projects.json
    for upsert_role.

    Mechanics:

    - Selected roles = BOOTSTRAP_ROLES ∩ mission_profile.roles_active.
      A profile that omits a fixed role skips it; a profile that adds one
      beyond the bootstrap set still needs Gru's deliberation to spawn it.
    - Each role's register_role call serializes the store mutation
      via the existing file-lock; the EACN3 registration HTTP and tmux
      spawn run concurrently.
    - Per-role failures are logged and recorded in the return value but
      do NOT abort project_create. The operator can re-spawn a
      missing role with mos role spawn <port> <role> (Gru's normal
      respawn path).

    Returns a list of (role_name, "ok"|"<error>") tuples for the
    caller to log.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from minions.lifecycle.role import BOOTSTRAP_ROLES, register_role

    profile_active = set(getattr(mission_profile, "roles_active", ()))
    selected = sorted(BOOTSTRAP_ROLES & profile_active)
    if not selected:
        logger.info(
            "bootstrap_fixed_roles: no fixed roles to pre-spawn for port=%d "
            "(profile.roles_active=%s)",
            port,
            sorted(profile_active),
        )
        return []

    logger.info(
        "bootstrap_fixed_roles: pre-spawning roles=%s for port=%d",
        selected,
        port,
    )

    def _spawn_one(role_name: str) -> tuple[str, str]:
        try:
            register_role(project_port=port, role=role_name, store=store)
            return role_name, "ok"
        except Exception as exc:
            logger.warning(
                "bootstrap_fixed_roles: role=%r port=%d spawn failed (non-fatal): %s",
                role_name,
                port,
                exc,
            )
            return role_name, str(exc)

    results: list[tuple[str, str]] = []
    # max_workers tracks `selected` so a profile with more bootstrap
    # roles in the future scales without code change.
    with ThreadPoolExecutor(max_workers=len(selected), thread_name_prefix="boot") as pool:
        futures = [pool.submit(_spawn_one, r) for r in selected]
        for fut in as_completed(futures):
            results.append(fut.result())
    logger.info(
        "bootstrap_fixed_roles: port=%d done results=%s",
        port,
        results,
    )
    return results


def bootstrap_generalist_expert(
    port: int,
    mission_profile: object,
    real_name: str,
    store: StateStore,
) -> tuple[str, str] | None:
    """Spawn one generalist Expert at project creation if the profile wants it.

    Expert is the project's single general worker (the "Common Agent"): it
    drives science AND carries the work out (code, experiments, paper,
    figures). Unlike the fixed roles it needs a *domain*; for the bootstrap
    worker we derive a neutral generalist domain from the project name so the
    team has a worker online immediately. Gru spawns additional specialist
    Experts later as the science demands.

    Returns (role_name, "ok"|"<error>") or None if the profile does
    not list expert in roles_active.
    """
    profile_active = set(getattr(mission_profile, "roles_active", ()))
    if "expert" not in profile_active:
        return None

    from minions.lifecycle.role import register_expert

    domain = f"{real_name} generalist"
    brief = (
        "You are the project's first, generalist Expert worker. Survey the "
        "project topic, propose the first concrete research step, and begin "
        "driving the work (code, experiments, analysis). Gru may spawn "
        "additional specialist Experts alongside you."
    )
    try:
        res = register_expert(
            project_port=port,
            domain=domain,
            init_brief=brief,
            store=store,
        )
        role_name = str(res.get("name", f"expert-{slugify(domain)}"))
        logger.info("bootstrap_generalist_expert: spawned %s for port=%d", role_name, port)
        return role_name, "ok"
    except Exception as exc:
        logger.warning(
            "bootstrap_generalist_expert: port=%d spawn failed (non-fatal): %s",
            port,
            exc,
        )
        return "expert", str(exc)


def project_create(
    real_name: str,
    venue: str | None = None,
    base_branch: str = "HEAD",
    upstream: str | None = None,
    brief: str | None = None,
    topic_doc: str | None = None,
    template_dir: str | None = None,
    profile: str | None = None,
    store: StateStore | None = None,
) -> ProjectEntry:
    """Create a new project, start its EACN3 backend, and register it.

    Steps:
    1. Allocate a free port.
    2. Load the mission profile (defaults to "scientific-paper").
    3. Create project_{port}/ directory tree.
    4. Create git worktree on branch minionsos/project-{port}.
    5. Start EACN3 backend subprocess; health-probe up to 20 s.
    6. Write meta.json with profile metadata.
    7. Register in projects.json.

    Args:
        profile: Mission profile name (e.g., "scientific-paper").
                 Defaults to "scientific-paper" if not specified.

    Returns the ProjectEntry for the new project.
    """
    from minions.paths import project_roles_workspace_dir, project_workspace_root
    from minions.profiles import get_default_profile, load_profile

    profile_name = profile or get_default_profile()
    mission_profile = load_profile(profile_name)

    _store = store or StateStore()
    port = _store.find_next_port()
    logger.info(
        "project_create name=%r port=%d venue=%r profile=%s",
        real_name,
        port,
        venue,
        profile_name,
    )

    try:
        cfg = load_gru_config()
        github_push_target = cfg.github_push_target
        github_push_branch_prefix = cfg.github_push_branch_prefix
    except Exception:
        github_push_target = None
        github_push_branch_prefix = None

    # Create per-project bare repo by seeding from the author repo's HEAD,
    # then add the main worktree (Gru's branch), which also seeds the Book
    # layout + shared surface directly on main (the standalone -shared branch
    # was eliminated in v23). Role worktrees are created lazily by
    # register_role and branch off the project's main branch.
    branch, pdir = _prepare_project_tree(port, base_branch)

    # Start backend with port-conflict retry.
    max_retries = 3
    for attempt in range(max_retries):
        try:
            proc = start_backend(port)
            wait_for_health(port)
            break
        except BackendError as exc:
            if attempt < max_retries - 1:
                logger.warning(
                    "Port %d unavailable (attempt %d/%d): %s",
                    port,
                    attempt + 1,
                    max_retries,
                    exc,
                )
                port = _store.find_next_port()
                branch, pdir = _prepare_project_tree(port, base_branch)
            else:
                raise

    # Register a server record with EACN3 so roles can register as agents.
    # Now FATAL: a silently-absent server breaks downstream role registration
    # and gru-inbox delivery, so fail loud rather than limp along.
    try:
        server_id, eacn3_server_token = register_server(port)
    except BackendError as exc:
        logger.error("Server registration failed (fatal): %s", exc)
        proc.terminate()
        raise

    # Register the "gru" EACN queue agent on this project's bus so that
    # role -> gru direct messages land in a real EACN inbox.
    # FATAL on failure: without it, every Role -> Gru EACN message is
    # silently dropped.
    try:
        gru_agent_id, gru_agent_token = register_gru_eacn_agent(port, server_id)
    except BackendError as exc:
        logger.error("Gru agent registration failed (fatal): %s", exc)
        proc.terminate()
        raise

    now = _now_iso()
    entry = ProjectEntry(
        port=port,
        real_name=real_name,
        status="active",
        created=now,
        venue=venue,
        upstream_branch=upstream or base_branch,
        current_branch=branch,
        workspace_root=str(project_workspace_root(port).resolve()),
        workspace_main=str(project_main_workspace(port).resolve()),
        workspace_roles_root=str(project_roles_workspace_dir(port).resolve()),
        workspace_shared=str(project_main_workspace(port).resolve()),
        github_push_target=github_push_target,
        github_push_branch_prefix=github_push_branch_prefix,
        active_roles=[],
    )
    # Store backend PID, server_id, and eacn3_server_token in extra fields.
    entry_dict = entry.model_dump()
    entry_dict["backend_pid"] = proc.pid
    entry_dict["eacn3_server_id"] = server_id
    entry_dict["eacn3_server_token"] = eacn3_server_token
    entry_dict["gru_agent_id"] = gru_agent_id
    entry_dict["gru_agent_token"] = gru_agent_token
    entry_dict["eacn_agent_map"] = identity_map_for_meta(port)
    entry_dict["workspace_root"] = str(project_workspace_root(port).resolve())
    entry_dict["workspace_main"] = str(project_main_workspace(port).resolve())
    entry_dict["workspace_roles_root"] = str(project_roles_workspace_dir(port).resolve())
    entry_dict["workspace_shared"] = str(project_main_workspace(port).resolve())
    entry_dict["github_push_target"] = github_push_target
    entry_dict["github_push_branch_prefix"] = github_push_branch_prefix
    # Persist mission profile so revive / role launch / evaluator can read it.
    entry_dict["profile"] = profile_name
    entry_dict["profile_roles_active"] = list(mission_profile.roles_active)
    entry_dict["profile_lightweight"] = mission_profile.lightweight
    entry_dict["profile_phase_schema"] = mission_profile.phase_schema
    entry_dict["profile_on_done"] = mission_profile.on_done
    entry_dict["profile_evaluation"] = dict(mission_profile.evaluation)
    entry_dict["profile_deliverable_schema"] = dict(mission_profile.deliverable_schema)
    entry_dict["profile_role_prompt_overlay"] = dict(mission_profile.role_prompt_overlay)
    # Persist external resource pointers so revive / downstream tools can see them.
    if topic_doc:
        entry_dict["topic_doc"] = topic_doc
    if template_dir:
        entry_dict["template_dir"] = template_dir

    # Write meta.json with extra fields.
    path = project_meta_json(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(entry_dict, indent=2), encoding="utf-8")
    os.replace(tmp, path)

    # Auto-generate project CLAUDE.md skeleton if not already present.
    claude_md = pdir / "CLAUDE.md"
    workspace_abs = str(project_main_workspace(port).resolve())
    if not claude_md.exists():
        claude_md.write_text(
            _project_templates.render_project_claude_md(
                port=port,
                real_name=real_name,
                venue=venue,
                branch=branch,
                workspace_abs=workspace_abs,
                brief=brief,
                topic_doc=topic_doc,
                template_dir=template_dir,
            ),
            encoding="utf-8",
        )
        logger.info("Wrote project CLAUDE.md skeleton: %s", claude_md)

    # Ensure branches/main/experiments/ exists so local experiment target resolves.
    try:
        (project_main_workspace(port) / "experiments").mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # non-fatal
        logger.warning("Could not create branches/main/experiments/: %s", exc)

    # Seed the Draft with a bootstrap node (B-000) as the project root.
    # This gives Roles a shared starting point and unifies cold-start with
    # the L1 memory layer. The bootstrap node contains the project brief,
    # expected roles, deliverable schema, and creation timestamp.
    try:
        seed_draft_bootstrap(
            port=port,
            profile_name=profile_name,
            mission_profile=mission_profile,
            real_name=real_name,
            brief=brief,
            topic_doc=topic_doc,
        )
    except Exception as exc:  # non-fatal
        logger.warning("Draft bootstrap seed failed (non-fatal): %s", exc)

    # Register in projects.json.
    _store.add_project(entry)

    # Pre-spawn the profile-active fixed roles in parallel. Without this, the live Gru process
    # has to issue a serial sequence of `mos_spawn_role` MCP calls — each
    # ~60-90s of Opus 4.7 deliberation — pushing the team's first useful
    # cycle ~5 min after project_create returns. Failures are recorded
    # but non-fatal; Gru can respawn anything missing.
    try:
        bootstrap_fixed_roles(port, mission_profile, _store)
    except Exception as exc:  # paranoid catch — function is non-fatal by design
        logger.warning(
            "project_create: fixed-role bootstrap raised (non-fatal); "
            "Gru will spawn the team via mos_spawn_role. error=%s",
            exc,
        )

    # Spawn one generalist Expert (the project's general worker) so the team
    # has a worker online immediately. Gru spawns specialist Experts later.
    try:
        bootstrap_generalist_expert(port, mission_profile, real_name, _store)
    except Exception as exc:  # non-fatal — Gru can spawn an Expert manually
        logger.warning(
            "project_create: generalist-Expert bootstrap raised (non-fatal); "
            "Gru will spawn an Expert via mos_spawn_expert. error=%s",
            exc,
        )

    logger.info("project_create done: port=%d pid=%d", port, proc.pid)
    return entry
