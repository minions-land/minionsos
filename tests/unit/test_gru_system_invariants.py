"""Pin two Gru-SYSTEM.md invariants so they survive future edits.

1. Gru is explicitly forbidden from hand-rolling EACN3 HTTP calls.
2. Gru is told to call ``gru_inbox_poll`` on activation / heartbeat to poll
   its project-local EACN queue through the MinionsOS adapter.

If either disappears, the dead-letter class of bugs we just fixed can quietly
return (role → Gru messages start being invisible again), so we lock them in.
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
        assert "gru_inbox_poll" in t
        assert "project-local EACN queue" in t
        assert "reliability shim" in t

    def test_uses_project_eacn_adapters_not_old_gru_protocol(self) -> None:
        t = _text()
        assert "project_eacn_send_message" in t
        assert "project_eacn_create_task" in t
        assert "gru_send_message" not in t
        assert "gru_publish_task" not in t

    def test_gru_does_not_broker_ordinary_role_to_role_work(self) -> None:
        t = _text()
        assert "not make Gru the mandatory router for ordinary role-to-role work" in t
        assert "owning Role" in t
        assert "task/message" in t
        assert "visible collaboration graph" in t

    def test_gru_delegates_system_maintenance_code_to_coder(self) -> None:
        t = _text()
        assert "Do not patch MinionsOS runtime code yourself" in t
        assert "System-maintenance delegation" in t
        assert "targeted `project_eacn_create_task` for Coder" in t
        assert "instead of patching it yourself" in t

    def test_forbids_periodic_idle_self_thinking(self) -> None:
        t = _text()
        assert "must not implement periodic idle self-thinking" in t
        assert "event-backed" in t

    def test_references_repair_command(self) -> None:
        # Operators must be told how to recover when the agent is missing.
        assert "mos project repair" in _text()
