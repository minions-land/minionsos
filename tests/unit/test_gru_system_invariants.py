"""Pin Gru-SYSTEM.md invariants so they survive future edits.

1. Gru is explicitly forbidden from hand-rolling EACN3 HTTP calls.
2. Gru's main EACN path for MinionsOS-internal work is the MOS Agent Pool
   (``mos_await_events`` / ``mos_send_message`` / ``mos_create_task``); raw
   ``eacn3_*`` is reserved for Global EACN3.
3. ``gru_inbox_poll`` is retained as a legacy / debug path, not the main
   loop. The prompt must still mention it so operators can use it.

If these disappear, the dead-letter class of bugs we fixed can quietly
return (role -> Gru messages start being invisible again), so we lock them
in.
"""

from __future__ import annotations

from pathlib import Path

GRU_SYSTEM = Path(__file__).resolve().parents[2] / "minions" / "roles" / "gru" / "SYSTEM.md"


def _text() -> str:
    return GRU_SYSTEM.read_text(encoding="utf-8")


class TestGruSystemInvariants:
    def test_file_exists(self) -> None:
        assert GRU_SYSTEM.exists(), f"missing: {GRU_SYSTEM}"

    def test_forbids_handcrafted_eacn_http(self) -> None:
        t = _text()
        assert "Do not call the EACN3 HTTP API by hand" in t
        # The cautionary clause about phantom 400s must travel with the rule.
        assert "phantom" in t.lower() or "signature mismatch" in t.lower()

    def test_documents_inbox_poll_habit(self) -> None:
        t = _text()
        # gru_inbox_poll is retained as a debug / recovery adapter. The prompt
        # keeps mentioning it so operators can reach for it when needed; the
        # main wake loop uses mos_await_events instead.
        assert "gru_inbox_poll" in t
        assert "mos_await_events" in t

    def test_uses_mos_agent_pool_for_internal_work(self) -> None:
        t = _text()
        # MOS Agent Pool is the single main entry for MinionsOS-internal
        # collaboration. Raw eacn3_* still exists (Gru is also a Global EACN3
        # terminal) but is scoped to Global.
        assert "mos_await_events" in t
        assert "mos_send_message" in t
        assert "mos_create_task" in t
        assert "mos_ack_clear" in t
        # The old protocol names must not leak back in.
        assert "gru_send_message" not in t
        assert "gru_publish_task" not in t

    def test_gru_does_not_broker_ordinary_role_to_role_work(self) -> None:
        t = _text()
        # Collapse consecutive whitespace so the assertion is tolerant of
        # line-wrap changes in the prompt.
        collapsed = " ".join(t.split())
        assert "not make Gru the mandatory router for ordinary role-to-role work" in collapsed
        assert "owning Role" in t
        assert "task/message" in t
        assert "visible collaboration graph" in t

    def test_gru_delegates_system_maintenance_code_to_coder(self) -> None:
        t = _text()
        assert "Do not patch MinionsOS runtime code yourself" in t
        assert "System-maintenance delegation" in t
        # Coder tasks now use the MOS Agent Pool rather than the legacy
        # project_eacn_* adapter path.
        assert "targeted `mos_create_task` for Coder" in t
        assert "instead of patching it yourself" in t

    def test_forbids_periodic_idle_self_thinking(self) -> None:
        t = _text()
        assert "must not implement periodic idle self-thinking" in t
        assert "event-backed" in t

    def test_references_repair_command(self) -> None:
        # Operators must be told how to recover when the agent is missing.
        assert "mos project repair" in _text()
