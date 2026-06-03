# MANUAL/ Auth List Update Plan

## Problem
MANUAL/tools/*.md files contain auth lists with retired roles:
- `coder` → should be `expert` 
- `writer` → should be `expert`
- `noter` → should be removed (or kept for backward compat tools like mos_issue_report)

## Affected Files Count
- Files with `coder` in auth: ~15-20
- Files with `writer` in auth: ~10-15
- Files with `noter` in auth: ~5

## Strategy
These are reference docs generated/maintained by MANUAL scripts. They describe tool authorization.

**Question**: Are these auto-generated or hand-maintained?
- If auto-generated: Fix the generator
- If hand-maintained: Bulk update needed

## Pattern to Update
```
OLD: auth: [gru, coder, ethics, writer, expert]
NEW: auth: [gru, ethics, expert]

OLD: auth: [coder]
NEW: auth: [expert]

OLD: auth: [writer]  
NEW: auth: [expert]

OLD: auth: [gru, coder, ethics, writer, expert, noter]
NEW: auth: [gru, ethics, expert]
```

## Special Cases
- `mos_issue_report` - lists all roles including noter (is this correct?)
- `mos_book_query` - same
- `mos_reset_context` - same
- `mos_publish_to_shared` - has table with noter subdirs

Need to verify if these tools actually still support "noter" for backward compat.
