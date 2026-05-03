"""Configuration models and loaders for MinionsOS V4.

Two config files are supported:

* ``minions/config/gru.yaml``  — global Gru settings.
* ``minions/config/experiment_targets.yaml``  — SSH / local execution targets.

Both files are gitignored; only ``*.yaml.example`` files are committed.
Loaders return sensible defaults when the file is absent.
"""

from __future__ import annotations

import enum
import logging
import os
import re
from pathlib import Path
from typing import Literal, cast

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
_WRITER_PAPER_SEARCH_TOOLS = [
    "search_arxiv",
    "search_pubmed",
    "search_biorxiv",
    "search_medrxiv",
    "search_google_scholar",
    "download_arxiv",
    "download_pubmed",
    "download_biorxiv",
    "download_medrxiv",
    "read_arxiv_paper",
    "read_pubmed_paper",
    "read_biorxiv_paper",
    "read_medrxiv_paper",
]


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
# "main" = the top-level role agent-host process; "subagent" = spawned sub-processes.
_WHITELIST: dict[tuple[str, str], list[str]] = {
    ("gru", "main"): [
        "gru_relay",
        "project_eacn_send_message",
        "project_eacn_create_task",
        "project_checkpoint_workspace",
        "gru_inbox_poll",
        "gru_start_monitor",
        "project_create",
        "project_kill",
        "project_close",
        "project_dormant",
        "project_revive",
        "project_set_phase",
        "project_list",
        "eacn3_*",
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
    (
        "noter",
        "main",
    ): ["eacn3_*", "Task", "WebSearch", "WebFetch", "Read"],
    ("noter", "subagent"): ["WebSearch", "WebFetch", "Read"],
    ("coder", "main"): [
        "eacn3_*",
        "Task",
        "project_checkpoint_workspace",
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
        "Task",
        "project_checkpoint_workspace",
        "exp_run",
        "exp_status",
        "exp_wait",
        "exp_kill",
        "exp_list",
        "exp_put",
        "exp_get",
        "exp_tail",
        "query_gpus",
        "exp_queue_*",
        "exp_gpu_pool_*",
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
        "exp_queue_*",
        "exp_gpu_pool_*",
        "WebSearch",
        "WebFetch",
        "Bash",
        "Read",
        "Write",
        "Edit",
    ],
    ("writer", "main"): [
        "eacn3_*",
        *_WRITER_PAPER_SEARCH_TOOLS,
        "Task",
        "project_checkpoint_workspace",
        "WebSearch",
        "WebFetch",
        "Bash",
        "Read",
        "Write",
        "Edit",
    ],
    ("writer", "subagent"): [
        *_WRITER_PAPER_SEARCH_TOOLS,
        "WebSearch",
        "WebFetch",
        "Bash",
        "Read",
        "Write",
        "Edit",
    ],
    ("expert", "main"): [
        "eacn3_*",
        "Task",
        "project_checkpoint_workspace",
        "WebSearch",
        "WebFetch",
        "Bash",
        "Read",
        "Write",
        "Edit",
    ],
    ("expert", "subagent"): ["WebSearch", "WebFetch", "Bash", "Read", "Write", "Edit"],
    ("reviewer", "main"): ["eacn3_*", "Task", "WebSearch", "WebFetch", "Read"],
    ("reviewer", "subagent"): ["WebSearch", "WebFetch", "Read"],
    ("ethics", "main"): ["eacn3_*", "Task", "WebSearch", "WebFetch", "Read"],
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
# Role classification and boundaries
# ---------------------------------------------------------------------------


class RoleType(enum.Enum):
    """Whether a role faces the human or the EACN coordination network."""

    human_side = "human_side"
    eacn_visible = "eacn_visible"


ROLE_CLASSIFICATION: dict[str, RoleType] = {
    "gru": RoleType.human_side,
    "noter": RoleType.human_side,
    "coder": RoleType.eacn_visible,
    "experimenter": RoleType.eacn_visible,
    "writer": RoleType.eacn_visible,
    "reviewer": RoleType.eacn_visible,
    "ethics": RoleType.eacn_visible,
    "expert": RoleType.eacn_visible,
}

ROLE_WRITE_BOUNDARIES: dict[str, list[str]] = {
    "gru": ["workspace/", "artifacts/", "memory/"],
    "noter": ["artifacts/notes/", "memory/"],
    "coder": ["workspace/", "memory/"],
    "experimenter": ["workspace/", "artifacts/", "memory/"],
    "writer": ["workspace/", "memory/"],
    "reviewer": ["artifacts/reviews/", "memory/"],
    "ethics": ["artifacts/ethics/", "memory/"],
    "expert": ["workspace/", "memory/"],
}


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
    project_parent_repo: str | None = Field(
        default=None,
        description=(
            "Optional git repository used as the source for project worktrees. "
            "When unset, MinionsOS uses MINIONS_ROOT.parent if it is a git repo, "
            "otherwise MINIONS_ROOT if that is a git repo."
        ),
    )
    projects_root: str | None = Field(
        default=None,
        description=(
            "Optional directory that contains project_<port>/ runtime trees. "
            "When unset, project directories live beside MINIONS_ROOT."
        ),
    )
    github_push_target: str | None = Field(
        default=None,
        description=(
            "Optional git remote URL or remote name used for durable workspace "
            "checkpoints. When unset, MinionsOS keeps commits local and skips git push."
        ),
    )
    github_push_branch_prefix: str = Field(
        default="minionsos",
        description="Branch prefix used when pushing durable checkpoints to github_push_target.",
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
    role_cooldown_seconds: int = Field(
        default=30,
        description="Minimum seconds between dispatches for the same role (any wakeup class).",
    )
    gru_hard_cooldown_seconds: int = Field(
        default=180,
        description="Hard Gru wake cooldown in seconds; Gru cannot be re-woken before this.",
    )
    gru_activity_window_seconds: int = Field(
        default=300,
        description=(
            "After hard cooldown and before this window, Gru wakes only when its "
            "project-local EACN queue has unread events."
        ),
    )
    gru_drive_interval_seconds: int = Field(
        default=300,
        description=(
            "Minimum seconds between autonomous Gru EACN drive wakeups when no "
            "Gru inbox entries are pending."
        ),
    )
    experiment_reconcile_interval_seconds: int = Field(
        default=30,
        description="Python-side Experimenter queue reconcile cadence in seconds.",
    )
    noter_report_interval: str = Field(
        default="30m",
        description="Default time-trigger cadence for Noter periodic project summaries.",
    )
    local_eacn_initial_balance: float = Field(
        default=10_000.0,
        description=(
            "Minimum local EACN credit balance ensured for Gru and registered project roles. "
            "MinionsOS still defaults project-local tasks to budget=0."
        ),
    )
    health_event_eacn_notifications: bool = Field(
        default=False,
        description=(
            "When true, Gru's health monitor also posts backend/role health events "
            "to project-local Gru and Noter queues. Structured health events are "
            "always written to project logs regardless of this flag."
        ),
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
    agent_host: Literal["claude", "codex"] = Field(
        default="codex",
        description="Default agent host for Gru and role wakeups: claude or codex.",
    )
    codex_model: str | None = Field(
        default=None,
        description="Optional Codex model name. When unset, Codex CLI config/default is used.",
    )
    codex_sandbox: Literal["read-only", "workspace-write", "danger-full-access"] = Field(
        default="danger-full-access",
        description=(
            "Codex sandbox mode for role wakeups when bypass is disabled. "
            "Default is danger-full-access so non-interactive local automation "
            "does not depend on platform sandbox support."
        ),
    )
    codex_approval_policy: Literal["untrusted", "on-request", "never"] = Field(
        default="never",
        description="Codex approval policy for non-interactive role wakeups.",
    )
    codex_reasoning_effort: Literal["low", "medium", "high", "xhigh"] = Field(
        default="xhigh",
        description="Codex reasoning effort for Gru and role wakeups.",
    )
    codex_bypass_approvals_and_sandbox: bool = Field(
        default=True,
        description=(
            "Use Codex --dangerously-bypass-approvals-and-sandbox for role wakeups. "
            "Enabled by default for unattended MinionsOS role automation; disable only "
            "when the local Codex sandbox is known to work reliably."
        ),
    )

    _KNOWN_MODELS: frozenset[str] = frozenset(
        {
            "claude-opus-4-7",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
        }
    )

    def model_registry_valid(self) -> tuple[bool, str]:
        """Return (ok, detail) for the configured model registry.

        Claude keeps the historical strict registry when explicitly selected.
        Codex model names are intentionally not hardcoded here; Codex CLI can
        use its own profile/config defaults when ``codex_model`` is unset.
        """
        if self.effective_agent_host() == "codex":
            model = self.codex_model or "<codex CLI default>"
            return True, f"codex host selected; model={model}; effort={self.codex_reasoning_effort}"
        if self.claude_model in self._KNOWN_MODELS:
            return True, f"{self.claude_model} is a known model"
        known = ", ".join(sorted(self._KNOWN_MODELS))
        return False, f"{self.claude_model!r} not in known models ({known})"

    def effective_agent_host(self) -> Literal["claude", "codex"]:
        """Return the configured host, allowing a process-local env override."""
        host = os.environ.get("MINIONS_AGENT_HOST", "").strip().lower() or self.agent_host
        if host not in {"claude", "codex"}:
            logger.warning(
                "Unknown MINIONS_AGENT_HOST=%r; falling back to configured agent_host=%s.",
                host,
                self.agent_host,
            )
            return self.agent_host
        return cast(Literal["claude", "codex"], host)

    # --- Scratchpad size thresholds (as fractions of the model context window) ---
    # Rationale: Context Rot / NoLiMa research shows effective context degrades
    # long before the nominal window is full, so we budget the scratchpad as a
    # percentage of the window rather than as an absolute token count. This lets
    # thresholds auto-scale with the underlying model.
    model_context_window_tokens: int = Field(
        default=1_000_000,
        description="Assumed context-window size of the underlying agent-host model (tokens).",
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
        description=(
            "Veto threshold (block normal event handling, attempt maintenance compaction, "
            "and alert Gru)."
        ),
    )

    @field_validator("poll_interval_default", mode="before")
    @classmethod
    def _valid_poll_interval(cls, v: object) -> object:
        allowed = {"1m", "3m", "5m"}
        if isinstance(v, str) and v.strip() in allowed:
            return v.strip()
        raise ValueError(f"poll_interval_default must be one of {sorted(allowed)}, got {v!r}")

    @field_validator("agent_host", mode="before")
    @classmethod
    def _valid_agent_host(cls, v: object) -> object:
        if isinstance(v, str):
            value = v.strip().lower()
            if value in {"claude", "codex"}:
                return value
        raise ValueError(f"agent_host must be 'claude' or 'codex', got {v!r}")

    @field_validator(
        "heartbeat_report_interval",
        "noter_report_interval",
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
        "experiment_reconcile_interval_seconds",
        "gru_hard_cooldown_seconds",
        "gru_activity_window_seconds",
        "gru_drive_interval_seconds",
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


def _config_path(config_dir: Path | None, filename: str) -> Path:
    """Resolve config path from a directory or direct YAML file path."""
    if config_dir is None:
        return CONFIG_DIR / filename
    path = Path(config_dir)
    if path.name == filename or path.suffix.lower() in {".yaml", ".yml"}:
        return path
    return path / filename


def load_gru_config(config_dir: Path | None = None) -> GruConfig:
    """Load and validate ``gru.yaml``, falling back to defaults if absent.

    Args:
        config_dir: Override the default ``minions/config/`` directory.
    """
    path = _config_path(config_dir, "gru.yaml")
    data = _load_yaml(path)
    try:
        return GruConfig(**data)
    except Exception as exc:
        raise ConfigError(f"Invalid gru.yaml: {exc}") from exc


def pin_effective_agent_host(config_dir: Path | None = None) -> Literal["claude", "codex"]:
    """Resolve the current host once and pin it in the process environment.

    Gru, the monitor sidecar, MCP servers, and role wakeups all inherit process
    environment. Pinning prevents a long-running process from drifting between
    Claude and Codex because a config file changed after startup.
    """
    host = load_gru_config(config_dir).effective_agent_host()
    os.environ["MINIONS_AGENT_HOST"] = host
    return host


def load_experiment_targets(config_dir: Path | None = None) -> ExperimentTargetsConfig:
    """Load and validate ``experiment_targets.yaml``, falling back to defaults.

    Args:
        config_dir: Override the default ``minions/config/`` directory.
    """
    path = _config_path(config_dir, "experiment_targets.yaml")
    data = _load_yaml(path)
    try:
        return ExperimentTargetsConfig(**data)
    except Exception as exc:
        raise ConfigError(f"Invalid experiment_targets.yaml: {exc}") from exc
