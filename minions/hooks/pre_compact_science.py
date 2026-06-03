#!/usr/bin/env python3
"""PreCompact hook — inject memory-layer-aware compaction instructions.

Scope: this hook only fires the science-compact prompt for **Role main
processes** (Noter / Coder / Writer / Ethics / Expert / domain experts
spawned via mos_spawn_expert). For every other surface — dev-Claude
hacking MinionsOS itself, the Gru supervisor, vanilla claude shells
that happened to land in this repo, or Role subagents — the hook
passthroughs ``custom_instructions`` so Claude Code uses its default
summarization. The Draft / Book prompt only makes sense when
the post-compact agent is the same Role main process re-entering its
forever-loop, and the resume contract (mos_draft_view →
mos_await_events) only makes sense in that exact
context. See ``_is_role_main()`` below for the gate.

Reads the hook input from stdin (JSON with ``trigger`` and ``custom_instructions``)
and prints science-aware ``/compact`` instructions to stdout. Claude Code uses
that text as the system message for the compact model, replacing the default
"summarize the conversation" prompt.

Design goals (in priority order):

1. Cost.  The compact summary is paid as input tokens on every subsequent
   turn until the next compact.  We push the model to **cite IDs and paths**
   instead of inlining node bodies, evidence text, Book pages, or
   experiment reports.  The agent re-fetches any of those in one MCP call
   (``mos_draft_view`` / ``mos_book_query``) far more cheaply than
   carrying them inline.

2. Cache safety.  This hook does not touch settings, working directory,
   tool definitions, or the system prompt — only the compact output text.
   The prompt-prefix cache key is unaffected, so the 5-minute prefix cache
   stays warm across the compact boundary.  The 1-hour extended cache (the
   ``ttl:"1h"`` patch this account runs) is also preserved for the same
   reason.

3. Recoverability.  ``mos_compact_context`` already persists pending plans
   to the Draft **before** scheduling ``/compact``.  This hook trusts
   the Draft / Book as ground truth and asks the compact
   model to produce a *pointer-shaped* summary, not a reconstructable
   transcript.

Per-role resume tool. The Resume_protocol block at the end of the
emitted instructions tells the post-compact role exactly what its
first tool call must be. EACN-registered roles drive their loop with
``mos_await_events``; Noter is the exception — it has no EACN agent
identity. The hook
reads ``MINIONS_ROLE_NAME`` from the env and emits the matching tool;
without this branching every Noter compact would tell Noter to call
a tool not in its whitelist and the role would park indefinitely
(GitHub Issue #30).

The output schema is parsed by ``post_compact_draft.py``.  Keep
section headings (``## Working_on``, ``## Next_action``,
``## New_or_changed_nodes``, ``## Pending_plans``, ``## Open_questions``,
``## Blocked_on``, ``## Dead_ends``, ``## Notes``) byte-stable across
edits.
"""

from __future__ import annotations

import json
import os
import sys


def _resume_tool() -> str:
    """Return the tool name the post-compact role must call first.

    Every role drives its event loop with ``mos_await_events`` (the timer-based
    noter loop was retired when Noter merged into Ethics).
    """
    return "mos_await_events"


# Roles where the science-compact prompt is the wrong shape:
#   - Gru is the supervisor, not a science agent. Its compact should keep
#     standard summarization, not be redirected to Draft / Book
#     and a forever-loop resume contract.
#   - Empty MINIONS_ROLE_NAME means this is a non-Role surface entirely
#     (dev-Claude editing MinionsOS itself, or a vanilla claude session
#     that happens to be inside the repo tree). Same logic applies.
#
# The gate also requires MINIONS_AGENT_TYPE='main'. Subagents inherit
# their parent role's env, so this distinguishes a Role main process
# (where the science compact is correct) from a subagent or a delegated
# child (where it would be misleading).
_SCIENCE_COMPACT_ROLES = {"ethics", "expert"}


def _is_role_main() -> bool:
    """True iff this hook is firing inside a Role main process.

    Role main processes have BOTH ``MINIONS_ROLE_NAME`` (a known science
    role) AND ``MINIONS_AGENT_TYPE=main`` set by ``role_launcher._role_env``.
    Returns False for: dev-Claude (no MinionsOS env at all), Gru (no main-
    role env in its launcher), Role subagents (inherit parent env but the
    science compact prompt is meant for the main loop's resume contract).
    """
    role = (os.environ.get("MINIONS_ROLE_NAME") or "").strip().lower()
    if not role:
        return False
    if role == "gru":
        return False
    agent_type = (os.environ.get("MINIONS_AGENT_TYPE") or "").strip().lower()
    # An empty MINIONS_AGENT_TYPE is treated as main when MINIONS_ROLE_NAME
    # is set — the launcher always sets both, but operator-debug shells
    # sometimes only set the role name. Be permissive on type so manual
    # role-revival sessions still get the Draft-aware compact.
    if agent_type and agent_type != "main":
        return False
    # Restrict to known science roles; anything else (e.g. a future role
    # not yet wired to the L1/L2/L3 memory) falls through to passthrough.
    return role.startswith("expert") or role in _SCIENCE_COMPACT_ROLES


SCIENCE_COMPACT_INSTRUCTIONS_TEMPLATE = """\
You are compacting a MinionsOS science-discovery agent's context. The agent has \
durable memory on disk in three layers — DO NOT inline content from any of \
them. Cite IDs and paths instead; the post-compact agent will re-fetch as \
needed in one MCP call.

The three on-disk memory layers (already persisted, NEVER duplicate):

L0 — Reel  (branches/<role>/reel/<session_id>/)
     Raw immutable subagent transcripts. Drill-down only; not wake-injected.
     - index.jsonl               — JSONL index of captured subagent outputs
     - transcripts/<task_id>.jsonl — verbatim session transcript per task

L1 — Draft  (branches/main/draft/draft.json)
     The single team process graph. Node IDs: H-### (hypothesis), E-### (experiment),
     R-### (result), D-### (decision), Q-### (question), DEAD-### (dead_end),
     I-### (insight), M-### (method), C-### (citation), A-### (assumption).

L2 — Book  (branches/main/book/)
     Main-branch paper-shaped output curated by Ethics from Draft.
     - book/index.md                 — catalog of all ingested pages
     - book/sources/<role>-<slug>.md — one page per ingested artifact (carries reel_ref)
     - book/contradictions/          — auto-detected claim conflicts

ALSO durable (DO NOT inline):
     - EACN events at events/<agent>.jsonl (cite by event_id / timestamp).
     - Experiment artefacts at branches/main/exp/exp-<id>/report.md.
     - Per-role plan documents at branches/<role>/plans/<role>-<slug>.md.

OUTPUT SHAPE — produce these sections in order, in markdown:

## Working_on
- Single line. {node_id or book path the agent is currently driving}.

## Next_action
- Single line. The exact next concrete step, ideally a tool call.
  After wakeup the agent will call mos_draft_view() then {RESUME_TOOL}();
  if a different first step is required, name it explicitly here.

## New_or_changed_nodes
- {node_id} — {one-line label} ({status})
  Only NEW IDs created this session, or IDs whose status changed. Status is
  one of: tentative, verified, refuted, abandoned, blocked, unverified.

## Pending_plans
- {node_id} — {one-line label}  (already persisted with metadata.pending_plan=true)
  Single events the agent dequeued from EACN but did not execute. The
  post-compact agent will see them via mos_draft_view() and run them
  before {RESUME_TOOL}().

## Open_questions
- {Q-### or free text} — {one-line}.

## Blocked_on
- {what is blocking next progress and which artefact / event id is the dependency}.

## Dead_ends
- {DEAD-### or one-line description} — {abandonment reason in ≤10 words}.

## Notes
- Free-form, ≤3 short bullets. Anything not on disk that the agent must
  remember (current intent, half-formed framing, in-flight reasoning).
  Do NOT restate things from L0/L1/L2 here.

HARD RULES
- Target ~500 tokens, hard cap 2000 tokens. Tighter is better.
- Reference IDs and paths only. NEVER paste node text, book page bodies,
  experiment report content, code listings, or tool output bodies.
- If you would write a paragraph of evidence, write the artifact path
  instead (e.g. "see exp/exp-042/report.md").
- If you would summarize a book page, cite its path
  (e.g. "see book/sources/coder-tokenizer.md").
- DISCARD: verbose tool outputs, intermediate chain-of-thought,
  repeated file contents, formatted code blocks, EACN message bodies,
  anything already in draft.json or book/.

RESUME PROTOCOL — END EVERY COMPACT SUMMARY WITH THIS BLOCK VERBATIM
(it gives the post-compact agent — the same Role process, just compressed
context — its first concrete next step. Without this block, Claude Code
treats the summary as a final-state assistant turn and the forever-loop
never re-arms; the role parks at the input prompt until manually kicked.
See GitHub Issue #9 for the failure mode.):

## Resume_protocol
After this summary lands, your IMMEDIATE next tool call MUST be:
  mos_draft_view()           # re-orient on persisted state
followed by:
  {RESUME_TOOL}()            # resume the wake loop
Do NOT emit any reasoning, narration, or other tool call before
mos_draft_view(). The forever-loop contract requires the very next
turn to re-enter the wake loop — anything else parks the Role.
"""


def main() -> None:
    try:
        raw = sys.stdin.read()
        existing = ""
        if raw.strip():
            data = json.loads(raw)
            if isinstance(data, dict):
                existing = data.get("custom_instructions", "") or ""
    except json.JSONDecodeError:
        # Fall through with empty existing instructions; we still want to
        # supply the science brief. Never block the compact.
        existing = ""

    # Scope gate: this hook installs the L0/L1/L2-aware compact prompt and
    # the "first tool call must be mos_draft_view then resume" contract.
    # Both are *only* correct for a science Role main process. For:
    #   - dev-Claude editing MinionsOS itself,
    #   - Gru (the supervisor, not a science agent),
    #   - vanilla claude in any directory above MinionsOS,
    # the right behavior is to NOT inject our science prompt — let Claude
    # Code use its default summarization. Passthrough preserves any
    # ``custom_instructions`` the operator already supplied via /compact.
    if not _is_role_main():
        sys.stdout.write(existing)
        return

    instructions = SCIENCE_COMPACT_INSTRUCTIONS_TEMPLATE.replace("{RESUME_TOOL}", _resume_tool())

    parts: list[str] = []
    if existing:
        parts.append(existing)
    parts.append(instructions)

    sys.stdout.write("\n\n".join(parts))


if __name__ == "__main__":
    main()
