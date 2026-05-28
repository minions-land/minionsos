from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .policy import QuotaPolicy
from .termination import QuotaTermination

logger = logging.getLogger(__name__)


@dataclass
class QuotaAccountant:
    policy: QuotaPolicy
    _tokens_used: int = field(default=0, init=False)
    _calls_made: int = field(default=0, init=False)
    _peak_context: int = field(default=0, init=False)
    _accomplished: str = field(default="", init=False)
    _remaining: str = field(default="", init=False)

    def record_tokens(self, count: int) -> None:
        self._tokens_used += count
        if count > self._peak_context:
            self._peak_context = count

    def record_call(self) -> None:
        self._calls_made += 1

    def set_progress(self, *, accomplished: str, remaining: str) -> None:
        self._accomplished = accomplished
        self._remaining = remaining

    def tokens_used(self) -> int:
        return self._tokens_used

    def calls_made(self) -> int:
        return self._calls_made

    def peak_context(self) -> int:
        return self._peak_context

    def _check_tokens(self) -> QuotaTermination | None:
        cap = self.policy.token_cap
        if cap is None or self._tokens_used < cap:
            return None
        return QuotaTermination(
            reason="token_cap",
            accomplished=self._accomplished,
            remaining=self._remaining,
        )

    def _check_calls(self) -> QuotaTermination | None:
        cap = self.policy.call_cap
        if cap is None or self._calls_made < cap:
            return None
        return QuotaTermination(
            reason="call_cap",
            accomplished=self._accomplished,
            remaining=self._remaining,
        )

    def check(self) -> QuotaTermination | None:
        return self._check_tokens() or self._check_calls()
