#!/usr/bin/env python3
"""PreCompact hook — inject memory-layer-aware compaction instructions.

Reads the hook input from stdin (JSON with ``trigger`` and ``custom_instructions``)
and prints science-aware ``/compact`` instructions to stdout. Claude Code uses
that text as the system message for the compact model, replacing the default
"summarize the conversation" prompt.

Design goals (in priority order):

1. Cost.  The compact summary is paid as input tokens on every subsequent
   turn until the next compact.  We push the model to **cite IDs and paths**
   instead of inlining node bodies, evidence text, wiki pages, or experiment
   reports.  The agent re-fetches any of those in one MCP call
   (``mos_dag_summary`` / ``mos_wiki_hot_get`` / ``mos_dag_query`` /
   ``mos_global_graph_query``) far more cheaply than carrying them inline.

2. Cache safety.  This hook does not touch settings, working directory,
   tool definitions, or the system prompt — only the compact output text.
   The prompt-prefix cache key is unaffected, so the 5-minute prefix cache
   stays warm across the compact boundary.  The 1-hour extended cache (the
   ``ttl:"1h"`` patch this account runs) is also preserved for the same
   reason.

3. Recoverability.  ``mos_compact_context`` already persists pending plans
   to the DAG **before** scheduling ``/compact``.  This hook trusts the DAG /
   Wiki / corpus_graph / global_graph as ground truth and asks the compact
   model to produce a *pointer-shaped* summary, not a reconstructable
   transcript.

The output schema is parsed by ``post_compact_dag.py``.  Keep section
headings (``## Working_on``, ``## Next_action``, ``## New_or_changed_nodes``,
``## Pending_plans``, ``## Open_questions``, ``## Blocked_on``,
``## Dead_ends``, ``## Notes``) byte-stable across edits.
"""

from __future__ import annotations

import json
import sys

SCIENCE_COMPACT_INSTRUCTIONS = """\
You are compacting a MinionsOS science-discovery agent's context. The agent has \
durable memory on disk in three layers — DO NOT inline content from any of \
them. Cite IDs and paths instead; the post-compact agent will re-fetch as \
needed in one MCP call.

The three on-disk memory layers (already persisted, NEVER duplicate):

L1 — Exploration DAG  (branches/shared/exploration/dag.json)
     Node IDs: H-### (hypothesis), E-### (experiment), R-### (result),
       D-### (decision), Q-### (question), DEAD-### (dead_end),
       I-### (insight), M-### (method), C-### (citation), A-### (assumption).

L2 — Wiki  (branches/shared/wiki/)
     - wiki/index.md                 — Noter-maintained catalog
     - wiki/hot.md                   — ~500-word rolling cache (auto-injected at wake)
     - wiki/sources/<role>-<slug>.md — one page per ingested artifact
     - wiki/contradictions/          — auto-detected claim conflicts (Ethics reads)

L3 — Structural index  (corpus_graph)
     - branches/shared/exploration/corpus_graph.json — local; node IDs like n42_xxx
     - ~/.minionsos/graphify-global.json — Gru-only cross-project; IDs prefixed p<port>_

ALSO durable (DO NOT inline):
     - EACN events at events/<agent>.jsonl (cite by event_id / timestamp).
     - Experiment artefacts at branches/shared/exp/exp-<id>/report.md.
     - Per-role plan documents at branches/<role>/plans/<role>-<slug>.md.

OUTPUT SHAPE — produce these sections in order, in markdown:

## Working_on
- Single line. {node_id or wiki path the agent is currently driving}.

## Next_action
- Single line. The exact next concrete step, ideally a tool call.
  After wakeup the agent will call mos_dag_summary() then mos_await_events();
  if a different first step is required, name it explicitly here.

## New_or_changed_nodes
- {node_id} — {one-line label} ({status})
  Only NEW IDs created this session, or IDs whose status changed. Status is
  one of: tentative, verified, refuted, abandoned, blocked, unverified.

## Pending_plans
- {node_id} — {one-line label}  (already persisted with metadata.pending_plan=true)
  Single events the agent dequeued from EACN but did not execute. The
  post-compact agent will see them via mos_dag_summary() and run them
  before mos_await_events().

## Open_questions
- {Q-### or free text} — {one-line}.

## Blocked_on
- {what is blocking next progress and which artefact / event id is the dependency}.

## Dead_ends
- {DEAD-### or one-line description} — {abandonment reason in ≤10 words}.

## Notes
- Free-form, ≤3 short bullets. Anything not on disk that the agent must
  remember (current intent, half-formed framing, in-flight reasoning).
  Do NOT restate things from L1/L2/L3 here.

HARD RULES
- Target ~500 tokens, hard cap 2000 tokens. Tighter is better.
- Reference IDs and paths only. NEVER paste node text, wiki page bodies,
  experiment report content, code listings, or tool output bodies.
- If you would write a paragraph of evidence, write the artifact path
  instead (e.g. "see exp/exp-042/report.md").
- If you would summarize a wiki page, cite its path
  (e.g. "see wiki/sources/coder-tokenizer.md").
- DISCARD: verbose tool outputs, intermediate chain-of-thought,
  repeated file contents, formatted code blocks, EACN message bodies,
  anything already in dag.json or wiki/.
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

    parts: list[str] = []
    if existing:
        parts.append(existing)
    parts.append(SCIENCE_COMPACT_INSTRUCTIONS)

    sys.stdout.write("\n\n".join(parts))


if __name__ == "__main__":
    main()
