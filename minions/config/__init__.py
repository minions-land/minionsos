"""Configuration models and loaders for MinionsOS V2.

Two config files are supported:

* ``minions/config/gru.yaml``  — global Gru settings.
* ``minions/config/experiment_targets.yaml``  — SSH / local execution targets.

Both files are gitignored; only ``*.yaml.example`` files are committed.
Loaders return sensible defaults when the file is absent.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from minions.errors import ConfigError
from minions.paths import CONFIG_DIR

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Slug utility
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9]+")

_DURATION_RE = re.compile(r"^\s*(\d+)\s*([smhd]?)\s*$", re.IGNORECASE)
_DURATION_UNITS = {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_duration(value: str | int) -> int:
    """Parse a duration string like ``"2h"``, ``"30m"``, ``"45s"``, ``"1d"`` or a
    bare integer to seconds. ``"0"``/``0`` disables (returns 0).

    Raises :class:`ConfigError` on malformed input.
    """
    if isinstance(value, int):
        if value < 0:
            raise ConfigError(f"Negative duration not allowed: {value!r}")
        return value
    if not isinstance(value, str):
        raise ConfigError(f"Unsupported duration type: {type(value).__name__}")
    m = _DURATION_RE.match(value)
    if not m:
        raise ConfigError(f"Invalid duration: {value!r} (expected '<N>[s|m|h|d]')")
    n, unit = m.group(1), m.group(2).lower()
    return int(n) * _DURATION_UNITS[unit]


def slugify(text: str) -> str:
    """Convert *text* to a lowercase hyphen-separated slug.

    Examples::

        >>> slugify("Deep Learning Architecture")
        'deep-learning-architecture'
        >>> slugify("NLP / Text Generation")
        'nlp-text-generation'
    """
    return _SLUG_RE.sub("-", text.lower().strip()).strip("-")


# ---------------------------------------------------------------------------
# Whitelist resolver
# ---------------------------------------------------------------------------

# Maps (role_name, agent_type) → list of allowed tool prefixes / names.
# "main" = the top-level Claude process; "subagent" = spawned sub-processes.
_WHITELIST: dict[tuple[str, str], list[str]] = {
    ("gru", "main"): [
        "eacn3_*",
        "gru_relay",
        "gru_inbox_poll",
        "project_create",
        "project_close",
        "project_dormant",
        "project_revive",
        "project_list",
        "spawn_role",
        "spawn_expert",
        "dismiss_role",
        "list_roles",
        "WebSearch",
        "WebFetch",
        "Bash",
        "Read",
        "Write",
        "Edit",
    ],
    ("gru", "subagent"): ["WebSearch", "WebFetch", "Bash", "Read", "Write", "Edit"],
    ("noter", "main"): ["eacn3_*", "WebSearch", "WebFetch", "Read"],
    ("noter", "subagent"): ["WebSearch", "WebFetch", "Read"],
    ("coder", "main"): [
        "eacn3_*",
        "WebSearch",
        "WebFetch",
        "Bash",
        "Read",
        "Write",
        "Edit",
    ],
    ("coder", "subagent"): ["WebSearch", "WebFetch", "Bash", "Read", "Write", "Edit"],
    ("experimenter", "main"): [
        "eacn3_*",
        "exp_run",
        "exp_status",
        "exp_wait",
        "exp_kill",
        "exp_list",
        "exp_put",
        "exp_get",
        "exp_tail",
        "query_gpus",
        "WebSearch",
        "WebFetch",
        "Bash",
        "Read",
        "Write",
        "Edit",
    ],
    ("experimenter", "subagent"): [
        "exp_run",
        "exp_status",
        "exp_wait",
        "exp_kill",
        "exp_list",
        "exp_put",
        "exp_get",
        "exp_tail",
        "query_gpus",
        "WebSearch",
        "WebFetch",
        "Bash",
        "Read",
        "Write",
        "Edit",
    ],
    ("writer", "main"): [
        "eacn3_*",
        "WebSearch",
        "WebFetch",
        "Bash",
        "Read",
        "Write",
        "Edit",
    ],
    ("writer", "subagent"): ["WebSearch", "WebFetch", "Bash", "Read", "Write", "Edit"],
    ("expert", "main"): [
        "eacn3_*",
        "WebSearch",
        "WebFetch",
        "Bash",
        "Read",
        "Write",
        "Edit",
    ],
    ("expert", "subagent"): ["WebSearch", "WebFetch", "Bash", "Read", "Write", "Edit"],
    ("reviewer", "main"): ["eacn3_*", "WebSearch", "WebFetch", "Read"],
    ("reviewer", "subagent"): ["WebSearch", "WebFetch", "Read"],
    ("ethics", "main"): ["eacn3_*", "WebSearch", "WebFetch", "Read"],
    ("ethics", "subagent"): ["WebSearch", "WebFetch", "Read"],
}


def resolve_whitelist(role: str, agent_type: Literal["main", "subagent"] = "main") -> list[str]:
    """Return the allowed-tools list for *role* and *agent_type*.

    Expert roles are stored as ``expert-<slug>``; this function normalises
    them to ``expert`` before lookup.

    Args:
        role: Role name, e.g. ``"noter"``, ``"expert-dl-arch"``.
        agent_type: ``"main"`` or ``"subagent"``.

    Returns:
        List of tool name patterns (may contain ``*`` wildcards).
    """
    normalised = "expert" if role.startswith("expert") else role
    key = (normalised, agent_type)
    if key not in _WHITELIST:
        logger.warning(
            "No whitelist entry for role=%s agent_type=%s; returning empty.", role, agent_type
        )
        return []
    return list(_WHITELIST[key])


def whitelist_csv(role: str, agent_type: Literal["main", "subagent"] = "main") -> str:
    """Return the whitelist as a comma-separated string for ``--allowed-tools``."""
    return ",".join(resolve_whitelist(role, agent_type))


# ---------------------------------------------------------------------------
# gru.yaml model
# ---------------------------------------------------------------------------


class GruConfig(BaseModel):
    """Settings loaded from ``minions/config/gru.yaml``."""

    heartbeat_report_interval: str = Field(
        default="3m",
        description="Heartbeat report interval (e.g. '30s', '5m', '2h'). '0' disables.",
    )

    @property
    def heartbeat_interval_seconds(self) -> int:
        """Parse ``heartbeat_report_interval`` to integer seconds."""
        return parse_duration(self.heartbeat_report_interval)

    allow_web_search: bool = Field(
        default=True,
        description="When False, web search tools are stripped from all role whitelists.",
    )
    log_level: str = Field(
        default="info",
        description="Logging level (debug, info, warning, error).",
    )
    base_branch: str = Field(
        default="HEAD",
        description="Default git base branch for new project worktrees.",
    )
    backend_crash_threshold: int = Field(
        default=3,
        description="Max backend crashes within crash_window_seconds before auto-restart stops.",
    )
    role_crash_threshold: int = Field(
        default=3,
        description="Max role crashes within crash_window_seconds before role is dismissed.",
    )
    crash_window_seconds: int = Field(
        default=3600,
        description="Rolling window (seconds) for crash counting (default 1 h).",
    )
    poll_interval_default: str = Field(
        default="1m",
        description="Default EACN polling cadence for spawned Roles (allowed: 1m / 3m / 5m).",
    )
    gru_eacn_agent_id: str = Field(
        default="gru",
        description=(
            "EACN agent_id used when system components (e.g. wakeup dispatcher) "
            "post messages to Gru."
        ),
    )
    claude_model: str = Field(
        default="claude-sonnet-4-6",
        description="Claude model name passed to the claude CLI (e.g. claude-sonnet-4-6).",
    )

    _KNOWN_MODELS: frozenset[str] = frozenset({
        "claude-opus-4-7",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
    })

    def model_registry_valid(self) -> tuple[bool, str]:
        """Return (ok, detail) for the configured claude_model."""
        if self.claude_model in self._KNOWN_MODELS:
            return True, f"{self.claude_model} is a known model"
        known = ", ".join(sorted(self._KNOWN_MODELS))
        return False, f"{self.claude_model!r} not in known models ({known})"

    # --- Scratchpad size thresholds (as fractions of the model context window) ---
    # Rationale: Context Rot / NoLiMa research shows effective context degrades
    # long before the nominal window is full, so we budget the scratchpad as a
    # percentage of the window rather than as an absolute token count. This lets
    # thresholds auto-scale with the underlying model.
    model_context_window_tokens: int = Field(
        default=1_000_000,
        description="Assumed context-window size of the underlying Claude model (tokens).",
    )
    scratchpad_soft_pct: float = Field(
        default=0.10,
        description="Soft threshold (gentle compression hint on wake-up).",
    )
    scratchpad_hard_pct: float = Field(
        default=0.15,
        description="Hard threshold (require compression before processing new events).",
    )
    scratchpad_veto_pct: float = Field(
        default=0.20,
        description="Veto threshold (refuse to spawn and alert Gru).",
    )

    @field_validator("poll_interval_default", mode="before")
    @classmethod
    def _valid_poll_interval(cls, v: object) -> object:
        allowed = {"1m", "3m", "5m"}
        if isinstance(v, str) and v.strip() in allowed:
            return v.strip()
        raise ValueError(f"poll_interval_default must be one of {sorted(allowed)}, got {v!r}")

    @field_validator(
        "heartbeat_report_interval",
        mode="before",
    )
    @classmethod
    def _valid_duration(cls, v: object) -> object:
        if isinstance(v, int):
            return str(v)
        if isinstance(v, str):
            parse_duration(v)  # raises ConfigError on bad input
            return v
        raise ValueError(f"heartbeat_report_interval must be str or int, got {type(v).__name__}")

    @field_validator(
        "backend_crash_threshold",
        "role_crash_threshold",
        "crash_window_seconds",
        mode="before",
    )
    @classmethod
    def _positive_int(cls, v: object) -> object:
        if isinstance(v, int) and v <= 0:
            raise ValueError("Must be a positive integer.")
        return v


# ---------------------------------------------------------------------------
# experiment_targets.yaml model
# ---------------------------------------------------------------------------


class LocalTarget(BaseModel):
    id: str
    type: Literal["local"]
    workdir: str = "./experiments"


class SSHTarget(BaseModel):
    id: str
    type: Literal["ssh"]
    host: str
    key: str
    workdir: str = "/data/exp"


ExperimentTarget = LocalTarget | SSHTarget


class ExperimentTargetsConfig(BaseModel):
    """Settings loaded from ``minions/config/experiment_targets.yaml``."""

    targets: list[ExperimentTarget] = Field(default_factory=list)

    def get_target(self, target_id: str) -> ExperimentTarget:
        """Return the target with *target_id*, raising ``ConfigError`` if absent."""
        for t in self.targets:
            if t.id == target_id:
                return t
        raise ConfigError(f"Unknown experiment target: {target_id!r}")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict:
    """Load a YAML file, returning an empty dict if the file does not exist."""
    if not path.exists():
        logger.debug("Config file not found, using defaults: %s", path)
        return {}
    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise ConfigError(f"Expected a YAML mapping in {path}, got {type(data).__name__}.")
        return data
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML parse error in {path}: {exc}") from exc


def load_gru_config(config_dir: Path | None = None) -> GruConfig:
    """Load and validate ``gru.yaml``, falling back to defaults if absent.

    Args:
        config_dir: Override the default ``minions/config/`` directory.
    """
    path = (config_dir or CONFIG_DIR) / "gru.yaml"
    data = _load_yaml(path)
    try:
        return GruConfig(**data)
    except Exception as exc:
        raise ConfigError(f"Invalid gru.yaml: {exc}") from exc


def load_experiment_targets(config_dir: Path | None = None) -> ExperimentTargetsConfig:
    """Load and validate ``experiment_targets.yaml``, falling back to defaults.

    Args:
        config_dir: Override the default ``minions/config/`` directory.
    """
    path = (config_dir or CONFIG_DIR) / "experiment_targets.yaml"
    data = _load_yaml(path)
    try:
        return ExperimentTargetsConfig(**data)
    except Exception as exc:
        raise ConfigError(f"Invalid experiment_targets.yaml: {exc}") from exc
