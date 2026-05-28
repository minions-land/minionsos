from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from agent_host.quota.accountant import QuotaAccountant
from agent_host.quota.policy import QuotaPolicy
from agent_host.quota.termination import QuotaTermination
from agent_host.runtime.digest import ToolOutputDigest
from agent_host.runtime.host import AgentHost
from agent_host.telemetry.spend import SpendSink


def _make_host(token_cap: int = 50_000, call_cap: int = 100) -> tuple[AgentHost, Path]:
    policy = QuotaPolicy(token_cap=token_cap, call_cap=call_cap)
    with tempfile.TemporaryDirectory() as tmp:
        sink_path = Path(tmp) / "spend.jsonl"
        sink = SpendSink(sink_path)
        host = AgentHost(session_id="test-session", policy=policy, sink=sink)
        return host, sink_path


# Gap A: test_termination_includes_recorded_progress

def test_termination_includes_recorded_progress() -> None:
    policy = QuotaPolicy(token_cap=100, call_cap=10)
    acct = QuotaAccountant(policy)
    acct.set_progress(accomplished="step 1 done", remaining="step 2 pending")
    acct.record_tokens(200)
    term = acct.check()
    assert term is not None
    assert term.accomplished == "step 1 done"
    assert term.remaining == "step 2 pending"
    assert "step 1 done" in term.summary()
    assert "step 2 pending" in term.summary()


def test_termination_without_progress_has_empty_fields() -> None:
    policy = QuotaPolicy(token_cap=100, call_cap=10)
    acct = QuotaAccountant(policy)
    acct.record_tokens(200)
    term = acct.check()
    assert term is not None
    assert term.accomplished == ""
    assert term.remaining == ""


# Gap B: test_tool_output_digest

def test_record_tool_output_digest_returns_digest() -> None:
    host, _ = _make_host()
    d = host.record_tool_output_digest("bash", {"cmd": "ls"}, "file1\nfile2\n")
    assert isinstance(d, ToolOutputDigest)
    assert d.tool_name == "bash"
    assert len(d.args_hash) == 16
    assert d.output_chars == len("file1\nfile2\n")
    assert not d.truncated


def test_record_tool_output_digest_truncation_flag() -> None:
    host, _ = _make_host()
    long_output = "x" * 5000
    d = host.record_tool_output_digest("bash", {}, long_output, max_chars=4096)
    assert d.truncated


def test_digest_count_in_finalize() -> None:
    host, _ = _make_host()
    host.record_tool_output_digest("bash", {"a": 1}, "out1")
    host.record_tool_output_digest("read", {"b": 2}, "out2")
    result = host.finalize()
    assert result["digest_count"] == 2


# Gap C: test_spend_summary_format

def test_spend_summary_format() -> None:
    policy = QuotaPolicy(token_cap=50_000, call_cap=100)
    with tempfile.TemporaryDirectory() as tmp:
        sink = SpendSink(Path(tmp) / "spend.jsonl")
        host = AgentHost(session_id="s1", policy=policy, sink=sink)
        # 26K/50K = 52% → crosses 50% threshold only
        host.record_tokens(26_000)
        # total 27K; peak stays 26K
        host.record_tokens(1_000)
        summary = host.spend_summary()
    assert summary == "27K/50K tokens, 1 summarizations at 50%, peak context 26K."


def test_spend_summary_in_finalize() -> None:
    policy = QuotaPolicy(token_cap=50_000, call_cap=100)
    with tempfile.TemporaryDirectory() as tmp:
        sink = SpendSink(Path(tmp) / "spend.jsonl")
        host = AgentHost(session_id="s2", policy=policy, sink=sink)
        host.record_tokens(38_000)
        result = host.finalize()
    assert "spend_summary" in result
    assert "K/" in result["spend_summary"]
