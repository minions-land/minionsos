#!/usr/bin/env python3
"""PostCompact hook — extract pointer-shaped notes from a compact summary.

Fires after Claude Code's ``/compact`` completes.  Reads the hook payload
from stdin (a JSON object with ``transcript_path``, ``trigger``,
``compactMetadata``, plus standard hook metadata).  The compact summary
text itself is **not** inlined on stdin — it lives in the session jsonl
as the next user message after the compact_boundary system event,
marked ``isCompactSummary: true``.  The hook walks ``transcript_path``
to recover that text.  See GitHub Issue #8 for the prior bug where the
hook silently no-op'd because it expected a non-existent
``compact_summary`` stdin field.

The summary is *pointer-shaped*: it cites Draft node IDs, Book
paths, experiment-report paths, EACN event ids, etc.  This hook does NOT
try to materialise content from those pointers.  It only walks the
summary, extracts:

  - new / changed Draft node ids           (## New_or_changed_nodes)
  - pending-plan node ids restated by the LLM   (## Pending_plans)
  - bare ``[H-001]`` / ``[E-002]`` etc. node refs anywhere in the body

…and appends a single ``post_compact_extract`` audit entry to the same
project journal that ``mos_compact_context`` writes to:

  project_<port>/branches/shared/draft/journal.jsonl

Why an audit-only entry rather than direct Draft mutation:

  ``mos_compact_context`` already persists pending plans to the Draft
  *before* scheduling ``/compact`` (see ``minions/tools/compact.py``).
  Mutating the Draft again from the post-compact summary would risk
  duplicating those nodes, since the compact model legitimately restates
  them in its output.  We therefore treat this hook as an audit /
  recovery trail: if the agent later needs to reconstruct what was
  in-flight when the compact happened, the journal has both the
  pre-compact ``compact`` entry (with persisted node ids) and the
  post-compact ``post_compact_extract`` entry (with whatever the LLM
  cited in its summary).

Cache safety: stdout / stderr only; no settings, no cwd, no system
prompt.  Does not affect the prompt-prefix cache key.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("post_compact_draft")

# Draft node-id prefixes — must stay aligned with TYPE_PREFIX in
# minions/tools/draft.py.  Keep this list permissive: missing a
# new prefix only makes the audit entry less informative; it never breaks
# anything.
NODE_PREFIXES = ("H", "E", "R", "D", "Q", "DEAD", "I", "M", "C", "A")
NODE_REF_RE = re.compile(rf"\b({'|'.join(NODE_PREFIXES)})-\d+\b")
SECTION_RE = re.compile(r"^##\s+([A-Za-z_]+)\s*$", re.MULTILINE)
WORKING_ON_RE = re.compile(r"^##\s+Working_on\s*\n([\s\S]*?)(?=\n##\s|\Z)", re.MULTILINE)
NEXT_ACTION_RE = re.compile(r"^##\s+Next_action\s*\n([\s\S]*?)(?=\n##\s|\Z)", re.MULTILINE)
PENDING_RE = re.compile(r"^##\s+Pending_plans\s*\n([\s\S]*?)(?=\n##\s|\Z)", re.MULTILINE)
NEW_NODES_RE = re.compile(r"^##\s+New_or_changed_nodes\s*\n([\s\S]*?)(?=\n##\s|\Z)", re.MULTILINE)
DEAD_ENDS_RE = re.compile(r"^##\s+Dead_ends\s*\n([\s\S]*?)(?=\n##\s|\Z)", re.MULTILINE)


def _draft_dir(port: int) -> Path | None:
    """Return ``project_<port>/branches/shared/draft`` if locatable.

    Avoids importing ``minions.paths`` so the hook also works in raw
    operator shells where the package isn't on sys.path.  The repo root
    is the parent of the directory holding this file's parent (i.e.
    ``minions/hooks/post_compact_draft.py`` → ``MinionsOS/``).
    """
    minions_root = os.environ.get("MINIONS_ROOT")
    if minions_root:
        repo_root = Path(minions_root).parent
    else:
        repo_root = Path(__file__).resolve().parent.parent.parent
    candidate = repo_root / f"project_{port}" / "branches" / "shared" / "draft"
    return candidate if candidate.is_dir() else None


def _journal_path(draft_dir: Path) -> Path:
    return draft_dir / "journal.jsonl"


def _draft_path(draft_dir: Path) -> Path:
    return draft_dir / "draft.json"


def _existing_node_ids(draft_path: Path) -> set[str]:
    if not draft_path.exists():
        return set()
    try:
        data = json.loads(draft_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.debug("could not read %s: %s", draft_path, exc)
        return set()
    ids: set[str] = set()
    for node in data.get("nodes", []):
        nid = node.get("id", "")
        if isinstance(nid, str) and nid:
            ids.add(nid)
    return ids


def _section_text(summary: str, pattern: re.Pattern[str]) -> str:
    m = pattern.search(summary)
    return m.group(1).strip() if m else ""


def _node_ids_in(text: str) -> list[str]:
    """Return Draft node ids cited in ``text``, deduped, in order of first occurrence."""
    seen: set[str] = set()
    out: list[str] = []
    for match in NODE_REF_RE.finditer(text):
        nid = match.group(0)
        if nid not in seen:
            seen.add(nid)
            out.append(nid)
    return out


def _structured_extract(summary: str) -> dict:
    """Pull the pointer-shaped fields out of a memory-layer-aware summary.

    Returns a dict shaped::

        {
            "working_on": "...",
            "next_action": "...",
            "new_or_changed_node_ids": [...],
            "pending_plan_node_ids": [...],
            "dead_end_node_ids": [...],
            "all_node_refs": [...],   # every Draft ref anywhere in the summary
            "sections_seen": [...],   # which ## headings we found
        }
    """
    sections = [m.group(1) for m in SECTION_RE.finditer(summary)]
    return {
        "working_on": _section_text(summary, WORKING_ON_RE),
        "next_action": _section_text(summary, NEXT_ACTION_RE),
        "new_or_changed_node_ids": _node_ids_in(_section_text(summary, NEW_NODES_RE)),
        "pending_plan_node_ids": _node_ids_in(_section_text(summary, PENDING_RE)),
        "dead_end_node_ids": _node_ids_in(_section_text(summary, DEAD_ENDS_RE)),
        "all_node_refs": _node_ids_in(summary),
        "sections_seen": sections,
    }


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _load_summary_from_transcript(transcript_path: str) -> str:
    """Walk the Claude Code session JSONL backwards for the compact summary.

    Claude Code's PostCompact hook stdin payload does NOT inline the summary
    text. It carries ``transcript_path``, ``trigger``, ``compactMetadata``,
    plus standard hook metadata. The compact summary text itself is the
    next user message after the ``compact_boundary`` system event in the
    transcript jsonl, marked ``isCompactSummary: true``.

    We walk the file from the end (compact summary is always the most-recent
    record of its kind by the time PostCompact fires) and return the body
    text of the first ``isCompactSummary`` user message we find. Returns
    "" when nothing matches — never raises.
    """
    if not transcript_path:
        return ""
    path = Path(transcript_path)
    if not path.is_file():
        log.debug("transcript_path does not point to a file: %s", transcript_path)
        return ""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        log.debug("could not read transcript %s: %s", path, exc)
        return ""
    for raw in reversed(lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict):
            continue
        if not rec.get("isCompactSummary"):
            continue
        # Body shape: {"role": "user", "content": "<summary md>"}
        # but content can be a list of blocks for some Claude Code variants.
        msg = rec.get("message") or {}
        content = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            chunks: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str):
                        chunks.append(text)
            if chunks:
                return "\n".join(chunks)
    return ""


def main() -> None:
    raw = sys.stdin.read()
    if not raw.strip():
        log.debug("empty stdin, nothing to do")
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.error("could not parse stdin as JSON: %s", exc)
        return
    if not isinstance(data, dict):
        log.error("stdin payload is not a JSON object")
        return

    # Resolve the compact summary text. Priority order:
    # 1. Inline `compact_summary` field on stdin (legacy / synthetic test path).
    # 2. Walk `transcript_path` backwards for the user message marked
    #    `isCompactSummary: true` — this is what Claude Code 2.x actually
    #    delivers.
    # If both fail, exit quietly: nothing to extract is normal during
    # warmup and not an error.
    summary = data.get("compact_summary", "") or ""
    if not (isinstance(summary, str) and summary.strip()):
        transcript_path = data.get("transcript_path") or ""
        if isinstance(transcript_path, str):
            summary = _load_summary_from_transcript(transcript_path)

    if not isinstance(summary, str) or not summary.strip():
        log.debug(
            "no compact summary found (neither stdin.compact_summary nor "
            "transcript_path resolved a summary) — nothing to extract"
        )
        return

    port_env = os.environ.get("MINIONS_PROJECT_PORT", "")
    if not port_env:
        log.debug("MINIONS_PROJECT_PORT not set, skipping")
        return
    try:
        port = int(port_env)
    except ValueError:
        log.error("MINIONS_PROJECT_PORT=%r is not an integer", port_env)
        return

    draft_dir = _draft_dir(port)
    if draft_dir is None:
        log.debug("no draft dir for project_%s, skipping", port)
        return

    extract = _structured_extract(summary)

    # Annotate which referenced ids already exist in the live Draft so
    # a human auditor can immediately see whether the compact summary cited
    # known nodes vs hallucinated ones.
    known_ids = _existing_node_ids(_draft_path(draft_dir))
    extract["unknown_node_refs"] = [n for n in extract["all_node_refs"] if n not in known_ids]
    extract["known_node_refs"] = [n for n in extract["all_node_refs"] if n in known_ids]

    entry = {
        "op": "post_compact_extract",
        "role": os.environ.get("MINIONS_ROLE_NAME", "unknown"),
        "trigger": data.get("trigger", ""),
        "timestamp": _now_iso(),
        "summary_chars": len(summary),
        "extract": extract,
    }

    journal = _journal_path(draft_dir)
    try:
        journal.parent.mkdir(parents=True, exist_ok=True)
        with journal.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        log.error("failed to append journal entry to %s: %s", journal, exc)
        return

    log.info(
        "post_compact_extract: %d node refs (%d known, %d unknown), %d new, %d pending",
        len(extract["all_node_refs"]),
        len(extract["known_node_refs"]),
        len(extract["unknown_node_refs"]),
        len(extract["new_or_changed_node_ids"]),
        len(extract["pending_plan_node_ids"]),
    )


if __name__ == "__main__":
    main()
