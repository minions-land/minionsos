"""Config loader facade — re-exports from ``minions.config`` with a path-based API.

The test suite imports ``minions.config.loader`` and calls
``load_gru_config(path)`` where *path* is a direct file path (not a dir).
This module adapts that interface.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from minions.config import (  # noqa: F401  (re-export)
    ConfigError,
    ExperimentTargetsConfig,
    GruConfig,
    slugify,
)
from minions.errors import ConfigError as _ConfigError


def load_gru_config(path: Path | None = None) -> GruConfig:
    """Load ``GruConfig`` from *path*.

    *path* may be:
    - A direct ``.yaml`` file path.
    - A directory (``gru.yaml`` is appended).
    - ``None`` → uses the default ``minions/config/gru.yaml``.
    """
    if path is None:
        from minions.paths import CONFIG_DIR

        path = CONFIG_DIR / "gru.yaml"
    elif path.is_dir():
        path = path / "gru.yaml"
    # else: path is a direct file path

    if not path.exists():
        return GruConfig()

    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise _ConfigError(f"Expected a YAML mapping in {path}.")
        return GruConfig(**data)
    except yaml.YAMLError as exc:
        raise _ConfigError(f"YAML parse error in {path}: {exc}") from exc
    except Exception as exc:
        raise _ConfigError(f"Invalid gru.yaml: {exc}") from exc
