"""Unit tests for library hot-cache wake-up injection."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from minions.lifecycle import agent_host
from minions.lifecycle.agent_host import HOT_CACHE_TRUNCATION_LINE, build_forever_loop_prompt


@pytest.fixture
def hot_cache_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[int, Path]:
    port = 41234
    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))
    monkeypatch.setenv("MINIONS_PROJECTS_ROOT", str(tmp_path))
    library = tmp_path / f"project_{port}" / "branches" / "shared" / "library"
    library.mkdir(parents=True)
    return port, library


def test_hot_cache_block_returns_none_when_missing(
    hot_cache_project: tuple[int, Path],
) -> None:
    _port, _library = hot_cache_project

    assert agent_host._hot_cache_block() is None


def test_hot_cache_block_returns_none_when_empty(
    hot_cache_project: tuple[int, Path],
) -> None:
    _port, library = hot_cache_project
    (library / "hot.md").write_text(" \n\t\n", encoding="utf-8")

    assert agent_host._hot_cache_block() is None


def test_hot_cache_block_includes_non_empty_content_verbatim(
    hot_cache_project: tuple[int, Path],
) -> None:
    _port, library = hot_cache_project
    content = "Current focus: transformer ablation.\nNext: verify runs.\n"
    (library / "hot.md").write_text(content, encoding="utf-8")

    block = agent_host._hot_cache_block()

    assert block is not None
    assert block.startswith("## [Hot Cache]\n")
    assert content in block
    assert block.endswith(content)


def test_hot_cache_block_truncates_above_four_kb(
    hot_cache_project: tuple[int, Path],
) -> None:
    _port, library = hot_cache_project
    content = "x" * (agent_host.HOT_CACHE_BYTE_LIMIT + 25)
    (library / "hot.md").write_text(content, encoding="utf-8")

    block = agent_host._hot_cache_block()

    assert block is not None
    assert block.endswith(f"\n{HOT_CACHE_TRUNCATION_LINE}\n")
    assert "x" * agent_host.HOT_CACHE_BYTE_LIMIT in block
    assert "x" * (agent_host.HOT_CACHE_BYTE_LIMIT + 1) not in block


def test_hot_cache_block_returns_none_on_unicode_decode_error(
    hot_cache_project: tuple[int, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    _port, library = hot_cache_project
    (library / "hot.md").write_bytes(b"\xff\xfe\xfa")

    with caplog.at_level(logging.WARNING, logger=agent_host.logger.name):
        assert agent_host._hot_cache_block() is None

    assert "failed to read library hot cache" in caplog.text


def test_forever_loop_prompt_includes_hot_cache_when_available(
    hot_cache_project: tuple[int, Path],
) -> None:
    _port, library = hot_cache_project
    (library / "hot.md").write_text("Hot fact: pending reviewer handoff.\n", encoding="utf-8")

    prompt = build_forever_loop_prompt(role_name="coder")

    assert "## [Hot Cache]" in prompt
    assert "Hot fact: pending reviewer handoff.\n" in prompt


def test_forever_loop_prompt_unchanged_when_hot_cache_absent(
    hot_cache_project: tuple[int, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port, _library = hot_cache_project
    baseline = build_forever_loop_prompt(role_name="coder", port=port)

    monkeypatch.setenv("MINIONS_PROJECT_PORT", str(port))
    prompt = build_forever_loop_prompt(role_name="coder")

    assert "## [Hot Cache]" not in prompt
    assert prompt == baseline
