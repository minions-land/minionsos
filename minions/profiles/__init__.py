"""Mission Profile system for MinionsOS.

A Mission Profile is a project-level manifest that declares:
- What deliverable the project produces (paper, answer, patch, etc.)
- Which roles are active at project creation
- How the deliverable is evaluated
- Per-role publish whitelist overrides
- Phase schema (scientific three-stage vs minimal)

Profiles decouple MinionsOS from the "always a paper" assumption, enabling
benchmark and榜单 scenarios (HLE, SWE-bench, etc.) without losing the
full Autonomous Scientific Discovery capability.
"""

from __future__ import annotations

import logging
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from minions.errors import ConfigError
from minions.paths import MINIONS_ROOT

logger = logging.getLogger(__name__)

PROFILES_DIR = MINIONS_ROOT / "minions" / "profiles"


class MissionProfile(BaseModel):
    """Project-level mission manifest.

    Attributes:
        name: Profile identifier (kebab-case).
        lightweight: If True, skip heavy infrastructure (e.g., Noter periodic).
        roles_active: Roles to spawn at project creation. Gru is always present.
        role_prompt_overlay: Per-role prompt overlay paths (relative to profiles/).
        deliverable_schema: Required deliverable paths and per-role publish whitelist.
        evaluation: Evaluation strategy and reference paths.
        phase_schema: Phase progression model (scientific_three_stage | minimal).
        on_done: Action when deliverable is submitted (shutdown_project | dormant | none).
    """

    name: str
    lightweight: bool = False
    roles_active: list[str] = Field(default_factory=lambda: ["gru", "noter", "coder", "ethics"])
    role_prompt_overlay: dict[str, str] = Field(default_factory=dict)
    deliverable_schema: dict[str, object] = Field(default_factory=dict)
    evaluation: dict[str, object] = Field(default_factory=dict)
    phase_schema: Literal["scientific_three_stage", "minimal"] = "scientific_three_stage"
    on_done: Literal["shutdown_project", "dormant", "none"] = "none"


def load_profile(name: str) -> MissionProfile:
    """Load a mission profile by name.

    Args:
        name: Profile name (e.g., "scientific-paper", "hle-answer").

    Returns:
        Loaded MissionProfile.

    Raises:
        ConfigError: If profile file not found or invalid.
    """
    profile_path = PROFILES_DIR / f"{name}.yaml"
    if not profile_path.exists():
        raise ConfigError(
            f"Mission profile '{name}' not found at {profile_path}. "
            f"Available profiles: {list_profiles()}"
        )

    try:
        with profile_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as exc:
        raise ConfigError(f"Failed to parse profile '{name}': {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"Profile '{name}' must be a YAML object, got {type(data).__name__}")

    try:
        profile = MissionProfile.model_validate(data)
    except Exception as exc:
        raise ConfigError(f"Profile '{name}' validation failed: {exc}") from exc

    logger.info("Loaded mission profile: %s (roles=%s)", name, profile.roles_active)
    return profile


def list_profiles() -> list[str]:
    """List available profile names."""
    if not PROFILES_DIR.exists():
        return []
    return sorted(p.stem for p in PROFILES_DIR.glob("*.yaml") if p.is_file())


def get_default_profile() -> str:
    """Return the default profile name."""
    return "scientific-paper"


__all__ = [
    "PROFILES_DIR",
    "MissionProfile",
    "get_default_profile",
    "list_profiles",
    "load_profile",
]
