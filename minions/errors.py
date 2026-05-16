"""MinionsOS typed exception hierarchy."""

from __future__ import annotations


class MinionsError(Exception):
    """Base exception for all MinionsOS errors."""


class ConfigError(MinionsError):
    """Configuration loading or validation error."""


class StateError(MinionsError):
    """State store read/write error."""


class PortError(MinionsError):
    """Port allocation or binding error."""


class ProjectError(MinionsError):
    """Project lifecycle error."""


class RoleError(MinionsError):
    """Role spawn/dismiss error."""


class AlreadyActive(RoleError):
    """Raised when trying to spawn a role that is already active."""


class BackendError(MinionsError):
    """EACN3 backend subprocess error."""


class ProjectBridgeError(MinionsError):
    """mos_project_bridge delivery error."""


class ExperimentError(MinionsError):
    """Experiment execution error."""


class CircuitBreakError(ExperimentError):
    """Raised when 3 consecutive same-script failures trip the circuit breaker."""
