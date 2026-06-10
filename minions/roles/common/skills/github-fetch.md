---
slug: github-fetch
summary: Read content from any GitHub repo without cloning. Default path is `gh api` + `base64 -d`; fall back to `gh repo clone --depth=1` for whole repos and `curl raw.githubusercontent.com` when `gh` is unavailable. Captures the host network constraints (github.com HTTPS throttled, api.github.com fine).
layer: logical
tools:
version: 1
status: active
references: github-push, minionsos-push, reliable-file-io
provenance: human+agent
---

# Skill — GitHub Fetch

Read-only counterpart to [[github-push]]. Use when a Role needs to look at, summarize, port, or copy material from a GitHub URL — a single file, a sub-tree, a folder of skills, an example.

## When to use

- Trigger phrases: "look at github.com/...", "pull these skills", "what's in this repo", "summarize this folder", "copy these files".
- A pasted GitHub URL with no other instruction.

**Skip when:**
- The user wants to push or PR — use [[github-push]] (or [[minionsos-push]] if inside MinionsOS).
- The content is already cloned locally — read it directly.
- You only need a single piece of metadata (one `gh api` call inline is fine, no skill needed).

## Host facts

Verified 2026-05-19:

- `gh` is installed and authenticated as `PoorOtterBob` (full repo scope). Confirm with `gh auth status` before trusting it.
- `api.github.com` is reachable in ~1 s. `gh api ...` is the fast path.
- `github.com` HTTPS is throttled (~250 KB/s, curl 28 timeouts). SSH to `git@github.com` works reliably; `gh repo clone` rewrites to SSH thanks to the global `insteadOf` config.
- Role-side `WebFetch` / `WebSearch` are typically unavailable. Use the Bash tool with `gh` or `curl`.

## Procedure

1. **Pick scope.** Single file → `gh api` + `base64 -d`. Sub-tree → recursive tree call + bulk fetch. Whole repo → `gh repo clone --depth=1`. Metadata only → `gh api repos/<o>/<r>`.
2. **Confirm reachability:**
   ```bash
   gh auth status 2>&1 | head -5
   gh api "repos/<owner>/<repo>" --jq '{name, default_branch, license: .license.spdx_id}'
   ```
3. **Single file:**
   ```bash
   gh api "repos/<owner>/<repo>/contents/<path>" --jq '.content' | base64 -d > <local-name>
   ```
4. **Sub-tree listing:**
   ```bash
   gh api "repos/<owner>/<repo>/git/trees/<branch>?recursive=1" \
     --jq '.tree[] | select(.path | startswith("<subdir>")) | "\(.type)\t\(.path)"'
   ```
   Then build a `fetch.sh` with an array of paths and loop. Do **not** inline a multi-file `gh api ... base64 -d` `for` chain directly in the Bash tool — zsh has eaten them in this environment.
5. **Whole repo (only when grep/run/build is needed):**
   ```bash
   gh repo clone <owner>/<repo> /tmp/<repo-slug> -- --depth=1
   ```
6. **No-gh fallback:**
   ```bash
   curl -sSL --max-time 30 \
     "https://raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>" \
     -o <local-name>
   ```
7. **Watch rate limit:** `gh api rate_limit --jq '.resources.core'`. Authenticated budget is 5000/h. For 100+ files, prefer `gh repo clone` over per-file `gh api`.

## Output

When reporting back: repo + branch + short commit SHA, where the bytes landed (`/tmp/<repo-slug>/...`), and the license. Flag license explicitly if the next step is to copy content into MinionsOS or shared docs — CC BY-NC, GPL, and missing LICENSE all change downstream choices.

## Pitfalls

- Don't `WebFetch` `github.com` — blocked/throttled. Use `gh api` or `raw.githubusercontent.com`.
- Don't paste long multi-line `gh api | base64 -d` loops directly into Bash — write `fetch.sh`.
- Don't forget `base64 -d` — the `.content` field is always base64.
- Don't full-clone large repos without `--depth=1`.
- Don't skip license check when the content is going into shared/ or a published artifact.

## When this skill fails — self-update protocol

This skill encodes the host's working path as of its last verification date. Network constraints, `gh` auth state, rate limits, and IP reputation drift. **If a step here stops working, the skill itself is what's stale — patch the document, not just the current cycle.**

When a step fails:

1. **Diagnose first.** Run `gh auth status`, `gh api rate_limit --jq '.resources.core'`, `curl -v --max-time 10 https://api.github.com/zen`, `curl -v --max-time 10 https://github.com/ 2>&1 | head -20`. Identify which assumption broke (auth? throttle? scope? DNS?).
2. **Find the next working path.** Walk the fallback ladder, or invent a new rung. Capture the exact command line that returned bytes.
3. **Patch this repository skill:** update
   `minions/roles/common/skills/github-fetch.md` with the new path as a
   fallback rung, pitfall, or updated host fact. Date-stamp it
   (`verified 2026-MM-DD`) so the next Role sees the same fix.
4. **Surface the change.** Note `github-fetch updated: <one-line diff>` in the EACN report or final reply so the patch can be audited and committed. Never amend the skill silently.

The skill is a **cumulative log of how to get bytes off GitHub from this host**, not a fixed protocol. Any failure that costs >2 minutes to work around belongs in here.

## Why this skill exists

Captures the recipe that finally worked when pulling `lavinigam-gcp/build-with-adk` on 2026-05-19, after `WebFetch` was blocked and an inline multi-line `gh api | base64 -d` loop was mangled by zsh. Future Role sessions land on the working path immediately instead of re-deriving it. The self-update protocol above ensures the next surprise gets the same treatment.
