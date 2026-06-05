from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HAN_RE = re.compile(r"[\u3400-\u9fff]")
SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "dist",
    "node_modules",
    "projects",
}
PROTECTED_PREFIXES = (Path("mcp-servers/eacn3"),)


def _markdown_files() -> list[Path]:
    proc = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.md"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    out: list[Path] = []
    for raw in proc.stdout.splitlines():
        rel = Path(raw)
        if any(rel == prefix or rel.is_relative_to(prefix) for prefix in PROTECTED_PREFIXES):
            continue
        path = ROOT / rel
        rel_parts = rel.parts
        if any(part in SKIP_DIRS for part in rel_parts):
            continue
        out.append(path)
    return sorted(out)


def test_markdown_chinese_prose_is_limited_to_readme_chinese_section() -> None:
    offenders: list[str] = []
    for path in _markdown_files():
        rel = path.relative_to(ROOT)
        text = path.read_text(encoding="utf-8")
        if rel == Path("README.md"):
            head, marker, _tail = text.partition("\n## 中文\n")
            assert marker, "README.md must keep an explicit Chinese-section marker"
            head = head.replace("[中文](#中文)", "")
            if HAN_RE.search(head):
                offenders.append(str(rel))
            continue
        if HAN_RE.search(text):
            offenders.append(str(rel))

    assert offenders == []


def test_root_markdown_files_are_named_in_markdown_index() -> None:
    index = (ROOT / "MARKDOWN_INDEX.md").read_text(encoding="utf-8")
    root_docs = sorted(path.name for path in ROOT.glob("*.md") if path.is_file())
    missing = [name for name in root_docs if f"`{name}`" not in index]
    assert missing == []
