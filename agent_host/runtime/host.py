from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from agent_host.quota.accountant import QuotaAccountant
from agent_host.quota.policy import QuotaPolicy
from agent_host.quota.termination import QuotaTermination
from agent_host.runtime.digest import ToolOutputDigest
from agent_host.telemetry.spend import SpendSink, SummarizationEvent

logger = logging.getLogger(__name__)


@dataclass
class AgentHost:
    session_id: str
    policy: QuotaPolicy
    sink: SpendSink
    _accountant: QuotaAccountant = field(init=False)
    _digests: list[ToolOutputDigest] = field(default_factory=list, init=False)
    _summarization_pcts: list[float] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self._accountant = QuotaAccountant(self.policy)

    def record_tokens(self, count: int) -> None:
        self._accountant.record_tokens(count)
        used = self._accountant.tokens_used()
        cap = self.policy.token_cap
        if cap:
            pct = used / cap
            for threshold in self.policy.warn_thresholds:
                if pct >= threshold and threshold not in self._summarization_pcts:
                    self._summarization_pcts.append(threshold)
                    event = SummarizationEvent(
                        session_id=self.session_id,
                        at_pct=threshold,
                        tokens_at_event=used,
                    )
                    self.sink.record_summarization(event)

    def record_call(self) -> None:
        self._accountant.record_call()

    def set_progress(self, *, accomplished: str, remaining: str) -> None:
        self._accountant.set_progress(accomplished=accomplished, remaining=remaining)

    def record_tool_output_digest(
        self, tool_name: str, args: dict, output: str, *, max_chars: int = 4096
    ) -> ToolOutputDigest:
        args_hash = hashlib.sha256(
            json.dumps(args, sort_keys=True).encode()
        ).hexdigest()[:16]
        truncated = len(output) > max_chars
        digest = ToolOutputDigest(
            tool_name=tool_name,
            args_hash=args_hash,
            output_chars=len(output),
            truncated=truncated,
        )
        self._digests.append(digest)
        return digest

    def spend_summary(self) -> str:
        used = self._accountant.tokens_used()
        cap = self.policy.token_cap
        used_k = round(used / 1000)
        cap_k = round(cap / 1000) if cap else 0
        peak_k = round(self._accountant.peak_context() / 1000)
        n = len(self._summarization_pcts)
        if n:
            pcts = ", ".join(str(round(p * 100)) for p in sorted(self._summarization_pcts))
            return f"{used_k}K/{cap_k}K tokens, {n} summarizations at {pcts}%, peak context {peak_k}K."
        return f"{used_k}K/{cap_k}K tokens, {n} summarizations at %, peak context {peak_k}K."

    def finalize(self) -> dict:
        term = self._accountant.check()
        return {
            "session_id": self.session_id,
            "tokens_used": self._accountant.tokens_used(),
            "calls_made": self._accountant.calls_made(),
            "peak_context": self._accountant.peak_context(),
            "digest_count": len(self._digests),
            "spend_summary": self.spend_summary(),
            "termination": term.summary() if term else None,
        }
