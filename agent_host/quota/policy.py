from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QuotaPolicy:
    token_cap: int
    call_cap: int
    warn_thresholds: tuple[float, ...] = (0.5, 0.7, 0.9)
