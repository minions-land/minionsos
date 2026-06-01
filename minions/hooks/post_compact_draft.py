#!/usr/bin/env python3
"""PostCompact hook — extract pointer-shaped notes from a compact summary.

Scope: this hook only runs the journal-extract + tmux-kick path for **Role
main processes** (Noter / Coder / Writer / Ethics / Expert / domain experts
spawned via mos_spawn_expert). For every other surface — dev-Claude
hacking MinionsOS itself, the Gru supervisor, vanilla claude shells, or
Role subagents that inherit MINIONS_PROJECT_PORT from their parent — the
hook short-circuits before touching the journal or tmux. See
``_is_role_main()`` below for the gate. The pre-compact hook
(``pre_compact_science.py``) uses the same gate; keep them aligned.

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
import shlex
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("post_compact_draft")

# Roles where the journal-extract + tmux-kick is meaningful. Mirrors
# pre_compact_science._SCIENCE_COMPACT_ROLES — keep the two lists aligned.
# Anything else (Gru, dev-Claude, vanilla shells, Role subagents) skips the
# hook entirely; they don't own a draft.json journal and don't drive a
# resumable forever-loop, so a journal write or tmux kick would be wrong.
_SCIENCE_COMPACT_ROLES = {"ethics", "expert"}


def _is_role_main() -> bool:
    """True iff this hook is firing inside a Role main process.

    Symmetric with pre_compact_science._is_role_main(). Without this gate,
    a Role subagent (which inherits MINIONS_PROJECT_PORT + MINIONS_ROLE_NAME
    from its parent) would write a spurious post_compact_extract entry
    *and* fire a tmux kick into its parent's pane every time the subagent
    itself ran out of context — a clear scope violation.
    """
    role = (os.environ.get("MINIONS_ROLE_NAME") or "").strip().lower()
    if not role:
        return False
    if role == "gru":
        return False
    agent_type = (os.environ.get("MINIONS_AGENT_TYPE") or "").strip().lower()
    if agent_type and agent_type != "main":
        return False
    return role.startswith("expert") or role in _SCIENCE_COMPACT_ROLES


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
    """Return ``projects/project_<port>/branches/shared/draft`` if locatable.

    Avoids importing ``minions.paths`` so the hook also works in raw
    operator shells where the package isn't on sys.path. Inlines the same
    resolution as ``minions.paths.projects_root()``: prefer
    ``MINIONS_PROJECTS_ROOT``, else ``MINIONS_ROOT/projects``, else fall
    back to the repo root inferred from this file's location.
    """
    projects_root_env = os.environ.get("MINIONS_PROJECTS_ROOT")
    if projects_root_env:
        projects_root = Path(projects_root_env)
    else:
        minions_root = os.environ.get("MINIONS_ROOT")
        if minions_root:
            repo_root = Path(minions_root)
        else:
            # minions/hooks/post_compact_draft.py -> MinionsOS/
            repo_root = Path(__file__).resolve().parent.parent.parent
        projects_root = repo_root / "projects"
    candidate = projects_root / f"project_{port}" / "branches" / "shared" / "draft"
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


def _kick_prompt() -> str:
    """Return the kick prompt to inject after compact.

    Imported lazily because hooks run in a minimal subprocess where importing
    the full ``minions`` package can fail on path-resolution edge cases. We
    duplicate the literal default if the import fails — worst-case the kick
    works but skips the ``/goal`` upgrade. Keep the literal aligned with
    ``parked_prompt.DEFAULT_KICK_PROMPT``.
    """
    try:
        from minions.lifecycle.parked_prompt import DEFAULT_KICK_PROMPT

        return DEFAULT_KICK_PROMPT
    except ImportError:
        return (
            "/goal Continue your event loop: stopping rule = your next "
            "mos_await_events() call returns with a real EACN event. Do not "
            "stop before then. Heartbeat must stay <60 s."
        )


def _kick_own_pane(port: int, role_name: str) -> bool:
    """Spawn a delayed background ``tmux send-keys`` into this role's pane.

    GitHub Issue #29: after Claude Code's ``/compact`` lands, the role
    parks at the input prompt — the resume-protocol text is a hint the
    model would obey *if* it got a turn, but no turn arrives until
    input does. We inject a Claude Code ``/goal`` slash command (see
    ``minions/lifecycle/parked_prompt.DEFAULT_KICK_PROMPT``) + Enter via
    tmux, on a 2-second delay so Claude Code finishes redrawing the
    prompt before keys land.

    The literal-string ``send-keys -l`` flag is the same path
    ``mos role kick`` uses (#17) — it bypasses the TUI's bracketed-paste
    interpretation, which is what makes the kick reliable.

    Returns True when the background process was successfully spawned,
    False otherwise. Failures are logged and swallowed — recovery is
    best-effort; the Gru-side parked-prompt nudger is the safety net.
    """
    if not role_name or role_name == "unknown":
        log.debug("post_compact_kick: role_name missing, skipping")
        return False
    session_name = f"mos-{port}-{role_name}"
    # Best-effort check that the session exists before queueing the kick.
    try:
        rc = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            capture_output=True,
            timeout=2.0,
        ).returncode
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        log.debug("post_compact_kick: tmux probe failed: %s", exc)
        return False
    if rc != 0:
        log.debug("post_compact_kick: session %s not alive, skipping", session_name)
        return False

    # The kick: 2 s grace, type the recovery prompt, half-second pause,
    # press Enter. Detached so the hook returns immediately.
    kick_cmd = (
        f"sleep 2 && "
        f"tmux send-keys -t {shlex.quote(session_name)} -l "
        f"{shlex.quote(_kick_prompt())} && "
        f"sleep 0.5 && "
        f"tmux send-keys -t {shlex.quote(session_name)} Enter"
    )
    try:
        subprocess.Popen(
            ["nohup", "bash", "-c", kick_cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except (FileNotFoundError, OSError) as exc:
        log.error("post_compact_kick: spawn failed: %s", exc)
        return False
    log.info("post_compact_kick: queued recovery kick for %s", session_name)
    return True


def _try_kick_from_env() -> bool:
    """Best-effort recovery kick using only env vars.

    Used by the early-return paths in :func:`main` so a parsing error or
    missing summary doesn't leave the role parked at the prompt — Issue
    #29 must be resolved regardless of whether the journal-extract path
    succeeded.
    """
    port_env = os.environ.get("MINIONS_PROJECT_PORT", "")
    role = os.environ.get("MINIONS_ROLE_NAME", "")
    if not port_env or not role:
        return False
    try:
        port = int(port_env)
    except ValueError:
        return False
    return _kick_own_pane(port, role)


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
    # Scope gate. Identical to pre_compact_science.py: only Role main
    # processes own a project draft journal and a resumable tmux pane.
    # For dev-Claude / Gru / Role subagents / vanilla shells the journal
    # write would be misleading and the tmux kick would target the wrong
    # session (or the parent of a subagent). Silent return preserves the
    # hook's "never block /compact" contract.
    if not _is_role_main():
        return

    raw = sys.stdin.read()
    if not raw.strip():
        log.debug("empty stdin, nothing to do")
        _try_kick_from_env()
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.error("could not parse stdin as JSON: %s", exc)
        _try_kick_from_env()
        return
    if not isinstance(data, dict):
        log.error("stdin payload is not a JSON object")
        _try_kick_from_env()
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
        _try_kick_from_env()
        return

    port_env = os.environ.get("MINIONS_PROJECT_PORT", "")
    if not port_env:
        log.debug("MINIONS_PROJECT_PORT not set, skipping")
        _try_kick_from_env()
        return
    try:
        port = int(port_env)
    except ValueError:
        log.error("MINIONS_PROJECT_PORT=%r is not an integer", port_env)
        return

    draft_dir = _draft_dir(port)
    if draft_dir is None:
        log.debug("no draft dir for project_%s, skipping", port)
        _kick_own_pane(port, os.environ.get("MINIONS_ROLE_NAME", "unknown"))
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

    # GitHub Issue #29: kick the role's own tmux pane so the resume-protocol
    # tool call actually fires. Without this the pane parks at the input
    # cursor and the agent never gets a turn to obey the resume contract.
    # Runs *after* the journal append so we never lose the audit trail
    # even if tmux is unavailable.
    _kick_own_pane(port, os.environ.get("MINIONS_ROLE_NAME", "unknown"))


if __name__ == "__main__":
    main()
