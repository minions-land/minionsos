"""MinionsOS — multi-agent workflow built on top of EACN3."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

# Single source of truth is pyproject.toml [project].version. Read it from the
# installed package metadata so __version__ can never drift from the package
# version again. The literal fallback only applies when running from a source
# tree that was never `uv sync`/`pip install`-ed; keep it in lockstep with
# pyproject.toml on every version bump.
try:
    __version__ = _pkg_version("minionsos")
except PackageNotFoundError:  # pragma: no cover - source tree without install metadata
    __version__ = "0.20.0"

