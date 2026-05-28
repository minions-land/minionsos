from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QuotaTermination:
    reason: str
    accomplished: str = ""
    remaining: str = ""

    def summary(self) -> str:
        parts = [self.reason]
        if self.accomplished:
            parts.append(f"accomplished: {self.accomplished}")
        if self.remaining:
            parts.append(f"remaining: {self.remaining}")
        return "; ".join(parts)
