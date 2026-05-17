---
slug: role-session-diff-timeline
summary: Open on every Noter wake before any other summary work — diff each role branch's archived session jsonl, stage timeline updates, publish to branches/shared/notes/timeline.md; never drain EACN3 queues.
layer: logical
tools: eacn3_list_tasks, eacn3_get_task, eacn3_get_messages, eacn3_list_agents, mos_publish_to_shared
version: 2
status: active
supersedes:
references: eacn3-mcp
provenance: human
---

# Skill — Role Session Diff Timeline

Every role wake leaves a jsonl transcript at `project_{port}/branches/<role>/.minionsos/sessions/<timestamp>-wake<NNN>.jsonl`. These are project-owned, git-tracked, and non-destructive to read. Noter scans them, summarises, appends to a staged timeline under `branches/noter/`, then publishes `branches/shared/notes/timeline.md` via `mos_publish_to_shared`.

## When to invoke

On every Noter wake, before any cadence-based or on-demand summary. The timeline is the source material for later summaries.

## Structure

Observation must be **read-only**. Never call `eacn3_get_events`, `eacn3_await_events`, or `eacn3_next` — those drain the network queues and steal events from the roles they belong to. Only non-destructive EACN3 reads (`eacn3_list_tasks`, `eacn3_get_task`, `eacn3_get_messages`, `eacn3_list_agents`) when the archive jsonl references an id worth enriching.

State across wakes is held in a cursor at `branches/noter/.session-scan-cursor.json`:

```json
{"role_name": "last-processed-archive-filename.jsonl", ...}
```

Cursor writes are atomic (`.tmp` + rename). Noter writes drafts and cursors under `branches/noter/`; published timeline output goes to `branches/shared/notes/` via `mos_publish_to_shared`.

## Procedure

1. **List role branch dirs** under `project_{port}/branches/` (every non-empty subdirectory except `shared/`).
2. **For each role dir, list `.minionsos/sessions/*.jsonl`** sorted by filename (filename starts with timestamp, so lexical sort = chronological).
3. **Read the scan cursor** at `branches/noter/.session-scan-cursor.json`.
4. **For each role, the new archives are the ones lexically greater** than the cursor value for that role. No cursor entry → process all archives for that role.
5. **For each new archive:**
   - Parse the jsonl one line at a time (each line is one message / event).
   - Extract user turns, assistant turns, and tool calls.
   - Produce 3–8 factual one-liner entries in the timeline log entry format defined in your SYSTEM.md: `[TIMESTAMP] EVENT_TYPE | agent: <role> | task: <id or -> | note: <factual one-liner>`.
6. **Append the block to a staged `branches/noter/timeline.md`**, headed by the archive file's name so each block is traceable.
7. **Publish the staged timeline** to `branches/shared/notes/timeline.md` with `mos_publish_to_shared`.
8. **Update the cursor file atomically** (write `.tmp`, then rename).

Every timeline line is `[derived: archive-file-path]` — you summarise an archive, not an original EACN event.

## Pitfalls

- **Don't drain EACN3.** If you reach for `eacn3_next` or `eacn3_get_events` out of habit, stop. Observation must be read-only.
- **Don't write into other role branches.** Branches belong to their owning roles; your draft write scope is `branches/noter/`, and shared output must go through `mos_publish_to_shared`.
- **Skip empty or malformed lines** in jsonl. Hosts (Claude / Codex) emit slightly different schemas; be defensive with `try / except` per line, not per file.
- **Dedup on `(role_name, archive_filename)` via the cursor.** If the cursor write races with a new wake, at worst you re-process the same archive on the next pass — idempotent appends are fine because filenames contain wake counters.
- **Don't block on archive count.** Thousands of old archives with no cursor → process at most 50 in one wake and update the cursor progressively; re-run next wake.
