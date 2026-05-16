"""Unit tests for mos_project_bridge message formatting.

Tests: mode=auto|quote|paraphrase, source_note injection.
"""

from __future__ import annotations

import pytest

bridge_mod = pytest.importorskip("minions.tools.project_bridge")
format_bridge_message = bridge_mod.format_bridge_message


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestModeQuote:
    def test_quote_wraps_content(self) -> None:
        result = format_bridge_message(
            content="Hello from project A", mode="quote", from_port=37596
        )
        assert "Hello from project A" in result
        # Quote mode should include some quotation marker
        assert ">" in result or '"' in result or "quote" in result.lower()

    def test_quote_includes_source_note(self) -> None:
        result = format_bridge_message(
            content="Some message",
            mode="quote",
            from_port=37596,
            source_note="from Coder on project-37596",
        )
        assert "from Coder on project-37596" in result


class TestModeParaphrase:
    def test_paraphrase_returns_string(self) -> None:
        result = format_bridge_message(
            content="The experiment failed due to OOM on GPU 0.",
            mode="paraphrase",
            from_port=37596,
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_paraphrase_includes_source_note(self) -> None:
        result = format_bridge_message(
            content="Some message",
            mode="paraphrase",
            from_port=37596,
            source_note="Experimenter",
        )
        assert "Experimenter" in result


class TestModeAuto:
    def test_auto_returns_string(self) -> None:
        result = format_bridge_message(content="Short message.", mode="auto", from_port=37596)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_auto_includes_content(self) -> None:
        result = format_bridge_message(
            content="Critical: reviewer accepted the paper.", mode="auto", from_port=37596
        )
        assert "reviewer" in result.lower() or "accepted" in result.lower()

    def test_auto_with_source_note(self) -> None:
        result = format_bridge_message(
            content="Update from project A",
            mode="auto",
            from_port=37596,
            source_note="Gru on project-37596",
        )
        assert isinstance(result, str)
        assert len(result) > 0


class TestInvalidMode:
    def test_invalid_mode_raises(self) -> None:
        with pytest.raises((ValueError, KeyError, Exception)):
            format_bridge_message(
                content="test",
                mode="invalid_mode",  # type: ignore[arg-type]
                from_port=37596,
            )


class TestPortMetadata:
    def test_from_port_in_output(self) -> None:
        result = format_bridge_message(content="ping", mode="quote", from_port=37596)
        # The formatted message should reference the source port somewhere
        assert "37596" in result

    def test_attribution_header_present(self) -> None:
        # Every bridged message must carry a "[Bridged from project-...]"
        # attribution header so downstream readers can trace origin.
        result = format_bridge_message(content="ping", mode="auto", from_port=37596)
        assert "Bridged from project-37596" in result
