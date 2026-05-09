# Skill - Role session diff timeline

Build the project's per-role activity timeline by diffing each role branch's
archived host session jsonl files, **without** calling any destructive EACN3
event tool.

## Operating rule

Every role wake leaves a jsonl transcript at
`project_<port>/branches/<role>/.minionsos/sessions/<timestamp>-wake<NNN>.jsonl`.
These files are **project-owned, git-tracked, and non-destructive to read**.
Your job is to scan them on each wake of your own, detect new files, summarize
what the role did, and append the summary to `artifacts/notes/timeline.md`.

You must **never** call `eacn3_get_events`, `eacn3_await_events`, or
`eacn3_next` as part of observation. Those drain the network queues and steal
events from the roles they belong to. Use only non-destructive EACN3 reads
(`eacn3_list_tasks`, `eacn3_get_task`, `eacn3_get_messages`,
`eacn3_list_agents`) when the archive jsonl references a task or message id
you want to enrich with context.

## Core move

1. List all role branch dirs under `project_<port>/branches/` (every non-empty
   subdirectory except `shared/`).
2. For each role dir, list files in `.minionsos/sessions/*.jsonl` sorted by
   filename (filename starts with timestamp so lexical sort == chronological).
3. Read the scan cursor at `artifacts/notes/.session-scan-cursor.json`. Format:
   ```json
   {"role_name": "last-processed-archive-filename.jsonl", ...}
   ```
4. For each role, the **new** archive files are the ones whose filename is
   lexically greater than the cursor value for that role. If the role has no
   cursor entry, process all archive files for that role.
5. For each new archive:
   - Parse the jsonl one line at a time (each line is one message / event).
   - Extract user turns, assistant turns, and tool calls.
   - Produce 3-8 factual one-liner entries in the timeline log entry format
     defined in your SYSTEM.md:
     `[TIMESTAMP] EVENT_TYPE | agent: <role> | task: <id or -> | note: <factual one-liner>`
6. Append the block to `artifacts/notes/timeline.md`, headed by the archive
   file's name so the source of each block is traceable.
7. Update the cursor file atomically (write to `.tmp` then rename).

## When to invoke

On every Noter wake, before any cadence-based or on-demand summary. The
timeline is the source material for later summaries.

## Pitfalls

- **Don't drain EACN3.** If you reach for `eacn3_next` or `eacn3_get_events`
  out of habit, stop. Observation must be read-only.
- **Don't write into role branches.** Branches belong to their owning roles;
  your write scope is `artifacts/notes/` only. Cursor file lives there too.
- **Skip empty or malformed lines** in jsonl. Each jsonl is written by a host
  (Claude / Codex) with its own schema; be defensive with `try/except` per
  line, not per file.
- **Dedup on (role_name, archive_filename) via the cursor.** If the cursor
  write races with a new wake, at worst you re-process the same archive on
  the next pass — idempotent timeline appends are fine because filenames
  contain wake counters.
- **Don't block on archive count.** If there are thousands of old archives
  and no cursor yet, process at most 50 in one wake and update the cursor
  progressively; re-run next wake.

## Output habit

Every timeline line you add is **[derived: archive-file-path]** because you
are summarizing an archive, not an original EACN event. Match the
evidence-first convention from the root constitution.
