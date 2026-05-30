"""Pin Gru-SYSTEM.md invariants so they survive future edits.

1. Gru is explicitly forbidden from hand-rolling EACN3 HTTP calls.
2. Gru drives its event loop with ``mos_await_events`` and addresses Roles
   via ``eacn3_send_message``. Tasks are a Role-to-Role contract; Gru is
   not on that contract — ``eacn3_create_task`` / ``eacn3_submit_*`` /
   ``eacn3_close_task`` / ``eacn3_team_*`` are server-side denied. The
   legacy MOS Agent Pool send/create wrappers stay out.

If these disappear, the dead-letter class of bugs we fixed can quietly
return (role -> Gru messages start being invisible again, or Gru starts
posting phantom tasks), so we lock them in.
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

    def test_uses_native_eacn3_send_message(self) -> None:
        t = _text()
        assert "eacn3_send_message" in t
        # The retired send/create wrappers must not come back.
        assert "gru_send_message" not in t
        assert "gru_publish_task" not in t
        assert "mos_send_message" not in t
        assert "mos_create_task" not in t
        assert "mos_ack_clear" not in t
        assert "gru_inbox_poll" not in t
        assert "project_eacn_send_message" not in t
        assert "project_eacn_create_task" not in t

    def test_explicitly_forbids_gru_task_post(self) -> None:
        """Gru must NOT instruct itself to post tasks/bids/results.

        The boundary lives in three places:
          - server-side authz row (`("gru","main")` in `_SERVER_AUTHZ`),
          - this prompt-side rule pinned here,
          - the unit test that pins the server-side row.

        Coda-epilogue p37596 incident 2026-05-26: when prompt and authz
        diverged, the model invented an HTTP fallback. Pin both sides.
        """
        t = _text()
        # The forbidden surface is named explicitly in the SYSTEM prompt.
        assert "Do not post EACN tasks, bids, or results" in t
        assert "Tasks are a Role-to-Role contract" in t
        # No Gru-side instruction should encourage eacn3_create_task as
        # the action Gru takes itself. Mentions in the FORBIDDEN context
        # (e.g. "NEVER eacn3_create_task", "Do not invite gru on
        # eacn3_create_task") are fine; mentions in the ACTION-VERB
        # context are not. Cheap proxy: every occurrence must have a
        # negation marker within ±2 lines.
        lines = t.splitlines()
        negation_markers = (
            "NOT",
            "Not ",
            "not post",
            "never",
            "Never",
            "NEVER",
            "do not",
            "Do not",
            "denied",
            "no `eacn3_create_task",
            "stay out",
            "phantom",
            "instead of",
            "not bid",
            "not invite",
        )
        for i, line in enumerate(lines):
            if "eacn3_create_task" not in line:
                continue
            window = "\n".join(lines[max(0, i - 2) : i + 3])
            assert any(m in window for m in negation_markers), (
                f"Gru SYSTEM near line {i + 1} mentions eacn3_create_task "
                f"without a nearby negation marker — that's the failure "
                f"mode the boundary is meant to prevent. Window:\n{window!r}"
            )

    def test_gru_does_not_broker_ordinary_role_to_role_work(self) -> None:
        t = _text()
        collapsed = " ".join(t.split())
        assert "not make Gru the mandatory router for ordinary role-to-role work" in collapsed
        assert "owning Role" in t
        assert "task/message" in t
        assert "visible collaboration graph" in t

    def test_gru_delegates_system_maintenance_code_to_coder(self) -> None:
        t = _text()
        collapsed = " ".join(t.split())
        assert "Do not patch MinionsOS runtime code yourself" in t
        assert "System-maintenance delegation" in t
        # The maintenance handoff goes via direct message — Coder posts
        # its own task, Gru does not.
        assert "eacn3_send_message" in t
        assert "Coder posts its own EACN task" in collapsed
        assert "instead of patching it yourself" in t

    def test_forbids_periodic_idle_self_thinking(self) -> None:
        t = _text()
        assert "must not implement periodic idle self-thinking" in t
        assert "event-backed" in t

    def test_references_repair_command(self) -> None:
        assert "mos project repair" in _text()

    def test_task_based_collaboration_mode_section(self) -> None:
        """Issue #86 / live-session lesson: Gru must push roles into
        task-based collaboration and NOT become the inter-role mailroom
        that DM-feeds tasks one by one."""
        t = _text()
        collapsed = " ".join(t.split())
        assert "Task-based collaboration mode" in t
        # The anti-pattern (DM-feeding tasks) must be named as wrong.
        assert "mailroom" in collapsed
        # The right move: nudge the OWNING role to post its own task chain.
        assert "owning" in collapsed.lower()
        assert "invited_agent_ids" in collapsed
        # The agent_id-is-the-role-name fact must be stated so roles don't
        # stall waiting for Gru to hand them an id map.
        assert "role name" in collapsed
        # Executor-side encouragement: bid / claim / retrieve.
        assert "claim" in collapsed and "retriev" in collapsed.lower()
