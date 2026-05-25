---
id: pitfall-opus-empty-input
kind: pitfall
domain: debug
auth: ['*']
source: CLAUDE.md:1
since: 2026-05-24
keywords: [opus, empty, input, validation, error, latex, cjk, heredoc, bash, write, edit]
related: []
status: stable
---

# pitfall: long CJK / LaTeX / heredoc → empty `tool_use.input` (Opus 4.7 bug)

**Symptom (`Paper Crash` 2026-05-24, referenced from `CLAUDE.md`):**
```
InputValidationError: required parameter 'command' is missing
output_tokens: 47, 74, 25
```
Three consecutive `Bash` calls with `cat <<'EOF' ... EOF` for a long Chinese
LaTeX comparison report. The model emitted `input: {}`. Output tokens were
tiny (47/74/25) — not a max_tokens or context-length issue. The model
silently bailed on the long structured field.

## Cause

Opus 4.7 has an observed failure mode where, for one tool_use whose argument
is a long CJK + LaTeX / heredoc / Markdown payload, it emits `input: {}`
instead of the actual fields.

## Hard cap

**~50 lines / ~3 KB per `tool_use.input`** for `Write.content`,
`Edit.new_string`, or `Bash.command` containing a heredoc.

## Recipe

For anything bigger:

1. **Seed the file** with one short `Write` (≤ 50 lines: preamble +
   closing token like `\end{document}`).
2. **Append rest** with successive `Edit` calls, each ≤ 50 lines, inserting
   before the closing token.
3. **Never** stuff a long doc into a Bash heredoc. The heredoc body becomes
   the oversize `Bash.command` string and triggers the same bug.

## Skill reference

`minions/roles/common/skills/reliable-file-io.md` (Tier 0: seed-and-Edit)
has the exact recipe. The `large_file_guard.py` PreToolUse hook auto-blocks
Write/Edit > 550 lines and steers you into the skill.

## Triggers (always assume Tier 0)

- Long CJK content
- LaTeX with math / multi-section structure
- Markdown reports > 200 lines
- Any artifact > 50 KB
