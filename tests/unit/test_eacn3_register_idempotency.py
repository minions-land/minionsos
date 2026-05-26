"""Pin the EACN3 plugin's idempotent eacn3_register_agent guard (Issue #36 FM1).

The plugin's eacn3_register_agent handler must treat a registration with a
caller-supplied agent_id as a *claim* when that agent already exists locally
or on the backend. Otherwise dismiss+respawn'd Roles enter an infinite
register → 409/422 → register loop and stop heart-beating, because the LLM
keeps retrying eacn3_register_agent on cold start while the plugin's local
disk-state never reflects success.

These are source-level pin tests — they assert the guard text is present in
both the .ts source and the compiled dist/server.js. They are intentionally
shallow (no Node subprocess spin-up); the behaviour test would require a
running EACN3 backend, which the unit test suite does not have.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "mcp-servers" / "eacn3" / "plugin"
SRC = PLUGIN / "server.ts"
DIST = PLUGIN / "dist" / "server.js"


class TestIdempotentRegisterAgentSource:
    def test_source_has_idempotency_guard_marker(self) -> None:
        text = SRC.read_text(encoding="utf-8")
        # The guard MUST be tied to a recognizable issue marker so it is not
        # accidentally removed during refactor.
        assert "Issue #36" in text, "source lost the Issue #36 marker"
        assert "idempotent_claim" in text, "idempotent_claim flag missing in source"

    def test_source_calls_claimAgent_when_agent_id_supplied(self) -> None:
        text = SRC.read_text(encoding="utf-8")
        assert "state.claimAgent(params.agent_id)" in text, (
            "register_agent must call claimAgent when params.agent_id is supplied "
            "so MinionsOS-pre-seeded plugin state short-circuits the loop"
        )

    def test_source_handles_409_422_from_backend(self) -> None:
        text = SRC.read_text(encoding="utf-8")
        # The backend may reject duplicate registration with 409/422 or an
        # "already" message; the guard must convert those to idempotent claim.
        assert "409|422" in text or "/409|422|already|conflict/i" in text, (
            "register_agent must accept 409/422/already errors as idempotent"
        )


class TestIdempotentRegisterAgentDist:
    """Ensure the dist build is in sync with the source — otherwise the
    fix exists in .ts but the running plugin is the unpatched .js."""

    def test_dist_contains_guard(self) -> None:
        assert DIST.exists(), "dist/server.js is missing — run npm run build"
        text = DIST.read_text(encoding="utf-8")
        assert "Issue #36" in text, "dist is stale — rebuild needed"
        assert "idempotent_claim" in text, "dist missing idempotent_claim"
        assert "claimAgent(params.agent_id)" in text, (
            "dist missing the claimAgent short-circuit — re-run npm run build"
        )
