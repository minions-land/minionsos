"""Logging configuration for MinionsOS V4.

Call ``configure_logging()`` once at process startup (e.g. from the MCP
server entry-point or the CLI).  Subsequent ``logging.getLogger(__name__)``
calls in any module will automatically inherit the configured handlers.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from minions.paths import GRU_LOG

_CONFIGURED = False

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s — %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def configure_logging(
    *,
    log_file: Path | None = None,
    force: bool = False,
) -> None:
    """Configure root logger with a console handler and a file handler.

    The log level is read from the ``MINIONS_LOG_LEVEL`` environment variable
    (default ``INFO``).  Pass *force=True* to reconfigure even if already set
    up (useful in tests).

    Args:
        log_file: Override the default log file path (``minions/state/logs/gru.log``).
        force: Re-apply configuration even if already called.
    """
    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    level_name = os.environ.get("MINIONS_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # Remove any handlers added by earlier calls or by basicConfig.
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # Console handler — always present.
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(formatter)
    root.addHandler(console)

    # File handler — write to gru.log; create parent dirs if needed.
    target: Path = log_file if log_file is not None else GRU_LOG
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(target, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError as exc:
        # Non-fatal: log to console only if the file can't be opened.
        logging.getLogger(__name__).warning(
            "Could not open log file %s: %s — logging to console only.", target, exc
        )

    _CONFIGURED = True
