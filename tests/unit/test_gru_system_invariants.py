"""Pin Gru-SYSTEM.md invariants so they survive future edits.

1. Gru is explicitly forbidden from hand-rolling EACN3 HTTP calls.
2. Gru drives its event loop with ``mos_await_events`` and writes to EACN3
   through native ``eacn3_send_message`` / ``eacn3_create_task``. The legacy
   MOS Agent Pool send/create wrappers stay out.

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
        assert "phantom" in t.lower() or "signature mismatch" in t.lower()

    def test_uses_native_eacn3_tools(self) -> None:
        t = _text()
        assert "eacn3_send_message" in t
        assert "eacn3_create_task" in t
        # The retired send/create wrappers must not come back.
        assert "gru_send_message" not in t
        assert "gru_publish_task" not in t
        assert "mos_send_message" not in t
        assert "mos_create_task" not in t
        assert "mos_ack_clear" not in t
        assert "gru_inbox_poll" not in t
        assert "project_eacn_send_message" not in t
        assert "project_eacn_create_task" not in t

    def test_gru_does_not_broker_ordinary_role_to_role_work(self) -> None:
        t = _text()
        collapsed = " ".join(t.split())
        assert "not make Gru the mandatory router for ordinary role-to-role work" in collapsed
        assert "owning Role" in t
        assert "task/message" in t
        assert "visible collaboration graph" in t

    def test_gru_delegates_system_maintenance_code_to_coder(self) -> None:
        t = _text()
        assert "Do not patch MinionsOS runtime code yourself" in t
        assert "System-maintenance delegation" in t
        assert "targeted `eacn3_create_task` for Coder" in t
        assert "instead of patching it yourself" in t

    def test_forbids_periodic_idle_self_thinking(self) -> None:
        t = _text()
        assert "must not implement periodic idle self-thinking" in t
        assert "event-backed" in t

    def test_references_repair_command(self) -> None:
        assert "mos project repair" in _text()
