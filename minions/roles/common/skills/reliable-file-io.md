---
slug: reliable-file-io
summary: Atomic alternative to Write/Edit. Trigger BEFORE writing on files >~200 lines, CJK/code-fences/math/heredoc-token content, paths where Write/Edit already failed this session, documents >~50KB, OR any CJK + LaTeX / multi-section structured report regardless of size. Tier 0 (CJK + LaTeX / heredoc-tokens / multi-section): seed-and-Edit only — no Bash heredoc, immune to the Opus 4.7 empty-input bug. Tier 1 atomic rename for ASCII single files; Tier 2 chunked pipeline with manifest + read-back verification for >50KB documents.
layer: physical
tools: Bash, Write, Edit
version: 2
status: active
supersedes: chunked-file-write
references: dispatcher-discipline
provenance: human+agent
---

# Reliable File IO — from single edits to long documents

## Scope

This skill covers THREE tiers of file writing reliability:

0. **Tier 0 — Seed-and-Edit** (mandatory for content shapes that trigger the Opus 4.7 empty-input bug): No Bash heredoc, no inline payload. Seed a skeleton via one short `Write`, then append every section via successive small `Edit` calls.

1. **Tier 1 — Atomic single-file IO** (replaces Write/Edit): For ASCII content where the built-in Write/Edit would stall, time out, or produce opaque errors. Uses Python `pathlib` + `atomic_write` inside a quoted Bash heredoc.

2. **Tier 2 — Long document pipeline** (replaces single-shot generation of large docs): For documents expected to exceed ~50KB. Uses a five-stage workflow: outline → chunked generation → read-back verification → assembly → final validation.

**Decision rule**:
- Content matches Tier 0 triggers (CJK, LaTeX math, heredoc-tokens like `EOF`/`PY`/`<<`, multi-section structured report) → **Tier 0**, regardless of total size.
- Otherwise, single ASCII file under ~50KB → Tier 1.
- Otherwise (>~50KB or multi-chapter) → Tier 2 (chunks written via Tier 0 if their shape triggers it, else Tier 1).

---

## Tier 0 — Empty-input failure on CJK + LaTeX / heredoc payloads (Opus 4.7) — READ FIRST

Opus 4.7 has a confirmed failure mode where a `tool_use` whose `input` field must carry a long CJK + LaTeX / heredoc / Markdown payload comes through with `input: {}`, and the harness rejects it with `InputValidationError: required parameter <field> is missing`. The failed turn shows tiny `output_tokens` (often <100), so it is NOT a max_tokens or context-length issue — the model silently bails on emitting the long structured field.

**This invalidates Tier 1's single Bash heredoc for CJK/LaTeX content even when total size is well under any heredoc limit.** The heredoc body becomes the oversize `Bash.command` string and triggers the same failure during emission.

### Mandatory recipe for CJK + LaTeX / multi-section reports / mixed CJK+math docs

Use Tier 0 whenever content matches **any** of: contains CJK; contains LaTeX math (`$...$`, `\begin{...}`); contains heredoc-style tokens (`EOF`, `PY`, `<<`); is a multi-section structured report (LaTeX paper, long Markdown report, long HTML).

1. **Seed a skeleton via one short `Write`** (≤ ~50 lines / ~3 KB total):
   - LaTeX: preamble + `\begin{document}` + section placeholders + `\end{document}`
   - HTML: `<head>` + boilerplate `<body>` + closing `</body></html>`
   - Markdown: title + table-of-contents stub + a final sentinel line you can target later
2. **Append every section via successive `Edit` calls**, each `new_string` ≤ ~50 lines / ~3 KB. Insert *before* the closing token (`\end{document}`, `</body>`, the final sentinel). Sections longer than that → split across 2–3 Edits.
3. **No Bash heredocs containing CJK + LaTeX payloads.** This explicitly overrides Tier 1's `python3 - <<'PY' ... PY` template for this content shape.
4. If atomicity is required, seed-and-Edit into `<target>.tmp` then `mv` at the end.

### When Tier 1's heredoc IS still safe

- ASCII-only content (no CJK, no smart quotes, no math) under ~3 KB
- Pure data dumps (JSON, CSV) under ~10 KB
- One-shot small config writes
- Python heredocs whose source is small and any CJK lives only in a small inline data dict

If in doubt → Tier 0. Seed-and-Edit is immune to this bug because every tool_use's `input` is small.

### Recovery from a live empty-input failure

1. Do NOT retry the same single-call approach (this is the third-failure-loop trap).
2. Switch to Tier 0 immediately, even mid-stream.
3. If the file does not yet exist on disk, just start Tier 0 from scratch. No state to recover.

### Confirmed failure case

`Paper Crash` 2026-05-24 — three consecutive empty-input failures in one Role-style session: (1) one `Write` of an entire Chinese LaTeX comparison report, (2) a Bash heredoc embedding the full Markdown report (Tier 1 path), (3) the same heredoc retried. cache_read 25K, output_tokens 47/74/25. Three failures in a row before user intervention.

---

## Pre-flight check (run BEFORE every Write / Edit)

**Any yes** → use this skill. Do not "try plain first."

**Size signals:**
- Content expected to exceed ~200 lines (single file) or ~50KB (total document)?
- Target file already > ~200 lines?

**Content shape signals:**
- CJK characters in non-trivial volume?
- 3+ code fences, `$math$` blocks, or many smart quotes / em-dashes?
- Literal `EOF`, `PY`, `MARK`, or `CHUNK_*` tokens?

**Edit fragility signals:**
- `old_string` > ~30 lines or has trailing whitespace / NBSP?
- `new_string` > ~50 lines or contains risky content shapes?

**Session state signals:**
- Has any Write or Edit on this path already failed this session?

**Document scale signals:**
- Is this a multi-chapter document (study notes, course material, reports)?
- Will the final output exceed ~50KB?
- Does the user need verification that all sections are present?

## Escalation rules

- **First failure on a path is a one-way door.** No retry with plain Write/Edit.
- **Don't escalate gradually.** If pre-flight trips, jump straight here.
- **Don't mix tools.** If part of a change needs this skill, use it for all parts.
- **Tier 0 trumps Tier 1 on shape, not size.** A 1KB Chinese LaTeX section still goes through Tier 0 — never a Bash heredoc.
- **Empty `input: {}` from a tool_use → switch to Tier 0 immediately.** Do not retry the same single-call write/heredoc, that's the documented loop trap.
- **Scale up, not down.** If you start with Tier 1 and realize the document is growing past 50KB, switch to Tier 2 for remaining content.

---

## Tier 1: Atomic Single-File IO

### The template

```bash
python3 - <<'PY'
from pathlib import Path
import os, tempfile

TARGET = Path("/abs/path/to/file.md")

def atomic_write(path: Path, text: str) -> None:
    tmp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=str(path.parent),
        prefix=f".{path.name}.", suffix=".tmp", delete=False
    )
    try:
        tmp.write(text)
        tmp.flush()
        os.fsync(tmp.fileno())
    finally:
        tmp.close()
    os.replace(tmp.name, path)

# --- operation goes here ---
PY
```

### Operations

**Generate (replaces Write):**
```python
parts = [
"""\
# Title

First section.
""",
"""\
## Section 2

Content with `code fences`, $math$, "smart quotes", and non-ASCII prose.
""",
]
atomic_write(TARGET, "".join(parts))
```

**Update by anchor (replaces Edit):**
```python
text = TARGET.read_text(encoding="utf-8")
anchor = "## Outline\n"
assert text.count(anchor) == 1, f"anchor not unique: {text.count(anchor)} matches"
start = text.index(anchor)
end   = text.index("\n## ", start + 1) + 1
text  = text[:start] + "## Outline (revised)\n\n- New point\n\n" + text[end:]
atomic_write(TARGET, text)
```

**Append (atomic — read-modify-write, never `open("a")`):**
```python
existing = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
atomic_write(TARGET, existing + "\n## Appendix\n\nNew material...\n")
```
> Plain `open("a")` is **not atomic** — a crash mid-write leaves a partial tail. Always go through `atomic_write` so the rename is the only externally visible state change.

### Pitfalls
- Always pass `encoding="utf-8"` explicitly.
- Assert `text.count(anchor) == 1` if anchor uniqueness is uncertain.
- Escape `"""` as `\"\"\"` or split across adjacent strings.
- Never run two heredocs concurrently on the same target.

---

## Tier 2: Long Document Pipeline (>50KB)

### When to use Tier 2

- Generating documents > 50KB (study materials, course notes, reports, standards)
- Multi-chapter structured documents (Markdown or LaTeX)
- Documents where completeness verification is critical
- Any scenario where a single Write would exceed tool limits

### The five-stage workflow

```
Stage 1: Planning
  ├─ Define document structure (outline)
  ├─ Estimate total size and chunk count
  ├─ Create project directory with chunks/ subdirectory
  ├─ Initialize manifest.json and checkpoint.json
  └─ Each chunk targets 5-15KB (hard max 20KB)

Stage 2: Chunked Generation
  ├─ Generate each chunk independently
  ├─ Write each chunk using Tier 1 atomic_write (NOT plain Write)
  ├─ Compute SHA256 for each chunk file
  ├─ Update manifest with chunk metadata
  ├─ Update checkpoint after each successful chunk
  └─ Chunk naming: chunk_{chapter}_{section}_{part}.md

Stage 3: Read-back Verification
  ├─ Read back every chunk file
  ├─ Verify SHA256 matches manifest
  ├─ Check chunk ordering is continuous
  ├─ Detect missing or duplicate chunks
  └─ Re-generate any failed chunks (return to Stage 2 for that chunk)

Stage 4: Assembly
  ├─ Sort chunks by manifest order
  ├─ Concatenate with section markers
  ├─ Write final file using Tier 1 atomic_write
  └─ Update checkpoint

Stage 5: Final Validation & Repair
  ├─ Read back final file
  ├─ Verify all chunk start-markers are present
  ├─ Validate structure (Markdown fences balanced, LaTeX environments matched)
  ├─ If issues found: identify affected chunk, re-generate, re-assemble
  └─ Output verification report
```

### Manifest format

```json
{
  "target_file": "document.md",
  "document_type": "markdown",
  "total_chunks": 12,
  "chunks": [
    {
      "chunk_id": "chunk_1_1_1",
      "order": 1,
      "heading": "## Section 1.1",
      "chunk_file": "chunks/chunk_1_1_1.md",
      "start_marker": "<!-- CHUNK_START: chunk_1_1_1 -->",
      "end_marker": "<!-- CHUNK_END: chunk_1_1_1 -->",
      "sha256": "abc123...",
      "status": "completed",
      "verified": true
    }
  ]
}
```

### Checkpoint format

```json
{
  "current_stage": "generation",
  "completed_chunks": ["chunk_1_1_1", "chunk_1_1_2"],
  "failed_chunks": [],
  "last_verified_chunk": "chunk_1_1_2",
  "assembly_status": "pending",
  "final_verification_status": "pending"
}
```

### Failure recovery

| Scenario | Detection | Recovery |
|----------|-----------|----------|
| Chunk write failed | manifest shows "pending" | Re-generate that chunk only |
| Final file truncated | Missing end markers | Re-assemble from chunks |
| SHA256 mismatch | Verification stage | Re-generate affected chunk |
| Markdown fences unbalanced | Final validation | Locate chunk, re-generate |
| LaTeX environments unmatched | Final validation | Locate chunk, re-generate |

### Key rules for Tier 2

- Every chunk write uses Tier 1's `atomic_write` template — never plain Write/Edit
- Never generate a single chunk > 20KB
- Always read back after writing — "tool call succeeded" ≠ "file is correct"
- Checkpoint after every successful chunk so work is never lost
- Use HTML comment markers for Markdown: `<!-- CHUNK_START: id -->`
- Use LaTeX comment markers for LaTeX: `% CHUNK_START: id`

---

## Prohibited actions (all tiers)

- ❌ Single Write/Edit call for content > 200 lines or > 50KB
- ❌ **Bash heredoc carrying CJK + LaTeX / multi-section payload, ever** — even if total bytes are small (this is the documented Opus 4.7 empty-input trigger)
- ❌ Retrying the same single-call Bash/Write after `InputValidationError: required parameter ... is missing` — switch to Tier 0
- ❌ Claiming file is complete without read-back verification
- ❌ Retrying plain Write/Edit after a failure on the same path
- ❌ Generating a chunk > 20KB
- ❌ Using `bash cat >>` as primary write method (Tier 1 fallback only)
- ❌ Assuming tool success means file correctness
- ❌ Mixing plain Write/Edit with this skill in one logical change

---

## Bash fallback (only when python3 is unavailable)

Write to a sibling tmp file, fsync, then `mv` — same atomic-rename guarantee as Tier 1, weaker durability.

```bash
TMP="$(mktemp "${FILE}.XXXXXX.tmp")"
cat > "$TMP" <<'EOF_PAYLOAD'
...content...
EOF_PAYLOAD
sync
mv -f "$TMP" "$FILE"
```

Never use `: > "$FILE"` followed by `cat >>` — that truncates the destination before any new bytes are written, so a crash mid-write loses the file.
