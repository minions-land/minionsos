"""Project-local EACN3 agent registration helpers."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from minions.config import load_gru_config
from minions.errors import BackendError
from minions.lifecycle import eacn_client
from minions.lifecycle.eacn_identity import upsert_agent_identity
from minions.paths import project_meta_json

logger = logging.getLogger(__name__)


def project_eacn_server_id(port: int, meta_path: Path | None = None) -> str:
    """Return the EACN3 server_id for a project.

    Role agents must be registered against the project's local EACN3 backend.
    The authoritative runtime server_id lives in ``project_{port}/meta.json``.
    """
    path = meta_path or project_meta_json(port)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BackendError(
            f"Cannot register project-local EACN agent: meta.json missing for port {port}."
        ) from exc
    except json.JSONDecodeError as exc:
        raise BackendError(
            f"Cannot register project-local EACN agent: meta.json is invalid for port {port}."
        ) from exc
    server_id = str(raw.get("eacn3_server_id") or "")
    if not server_id:
        raise BackendError(
            f"Cannot register project-local EACN agent: eacn3_server_id missing for port {port}."
        )
    return server_id


def _normalise_role(role_name: str) -> str:
    from minions.config import normalise_role_name

    return normalise_role_name(role_name)


def role_agent_domains(role_name: str) -> list[str]:
    """Return discovery domains for a MinionsOS project role."""
    base = _normalise_role(role_name)
    specific = {
        "coder": [
            "coding",
            "debugging",
            "implementation",
            "experiments",
            "execution",
            "evaluation",
        ],
        "writer": ["writing", "paper", "latex"],
        "ethics": [
            "evidence",
            "audit",
            "validation",
            "adjudication",
            "review",
            "critique",
        ],
        "expert": ["expert", "research", "analysis"],
    }.get(base, ["coordination"])
    return ["minionsos", "project-local", f"role:{base}", *specific]


def role_agent_tier(role_name: str) -> str:
    base = _normalise_role(role_name)
    if base in {"expert", "ethics"}:
        return "expert"
    return "general"


def role_agent_description(role_name: str) -> str:
    base = _normalise_role(role_name)
    descriptions = {
        "coder": (
            "Project-local Coder role for implementation, debugging, code handoffs, "
            "experiment execution, and result reporting."
        ),
        "writer": "Project-local Writer role for paper drafting and evidence-grounded revisions.",
        "ethics": "Project-local Ethics role for evidence validation and claim audit.",
        "expert": "Project-local Expert role for domain analysis and research guidance.",
    }
    return descriptions.get(base, f"Project-local MinionsOS role agent: {role_name}.")


def register_project_role_agent(
    port: int,
    role_name: str,
    *,
    server_id: str | None = None,
) -> tuple[str, list[str]]:
    """Register *role_name* as an AgentCard on the project's Local EACN3 network."""
    sid = server_id or project_eacn_server_id(port)
    domains = role_agent_domains(role_name)
    tier = role_agent_tier(role_name)
    description = role_agent_description(role_name)
    token, seeds = eacn_client.register_agent(
        port=port,
        agent_id=role_name,
        name=role_name,
        server_id=sid,
        domains=domains,
        skills=[
            {
                "name": f"minionsos.{_normalise_role(role_name)}",
                "description": description,
                "parameters": {"role": role_name, "project_port": port},
            }
        ],
        description=description,
        tier=tier,
    )
    try:
        minimum = load_gru_config().local_eacn_initial_balance
        eacn_client.ensure_balance(port, role_name, minimum)
    except Exception as exc:
        # Balance seeding is a resilience convenience. Role registration itself
        # is still the critical path; callers will surface create-task failures.
        logger.warning(
            "Could not seed local EACN balance for role=%s port=%d: %s",
            role_name,
            port,
            exc,
        )
    upsert_agent_identity(
        port,
        role_name=role_name,
        agent_id=role_name,
        kind="role",
        server_id=sid,
        agent_token=token,
        domains=domains,
        tier=tier,
        description=description,
        name=role_name,
    )
    return token, seeds
