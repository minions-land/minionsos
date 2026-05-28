# API Stability Policy

MinionsOS uses a three-tier stability classification for all public surfaces.
Breaking changes to **stable** surfaces require a minor-version bump and a
one-release deprecation alias. **Experimental** surfaces may change in any
patch. **Internal** surfaces carry no compatibility guarantee.

---

## Stability tiers

| Tier | Definition |
|---|---|
| **stable** | Semver-bound. Removals and incompatible changes require deprecation alias for ≥ 1 minor release before removal. |
| **experimental** | Under active development. Interface may change in any patch release without prior notice. |
| **internal** | Implementation detail. No compatibility guarantee across any release. |
| **deprecated** | Scheduled for removal. Deprecation alias present; removal no earlier than next minor. |

---

## Surface classification

| Surface | Tier | Notes |
|---|---|---|
| `mos_*` MCP tools (FastMCP stdio) | stable | Used by all Role processes; all tool names, parameter names, and return shapes are semver-bound. |
| `mos` CLI commands (`mos project`, `mos role`, `mos logs`, `mos doctor`, `mos viz`) | stable | Exit codes and stdout JSON schema (`--json`) are semver-bound. |
| `eacn3_*` MCP tools | stable | Network protocol surface; MinionsOS treats EACN3 as an external pinned dep. Changes tracked in `mcp-servers/eacn3/`. |
| Role SYSTEM.md prompt contracts | stable (versioned) | §-numbered sections are the versioned unit. Backward-incompatible section changes increment the contract version noted in `minions/roles/SYSTEM.md`. |
| `minions/errors.py` exception hierarchy | stable | Public exception names and parent relationships are semver-bound; `MinionsError` is the root. |
| `minions/profiles/*.yaml` schema | stable | `MissionProfile` fields used in existing profiles. New optional fields may be added in any patch. |
| `mcp-servers/eacn3/` package | external (pinned) | Treated as an upstream dep pinned in `pyproject.toml` + `uv.lock`. MinionsOS does not own its stability. |
| `minions/tools/mcp/` FastMCP server | internal | Import paths and decorator usage are not public API. Use MCP tools via the stdio protocol instead. |
| `minions/lifecycle/*.py` Python API | internal | Callable from tests only; not a supported public import surface. |
| `minions/config/__init__.py` whitelist constants | internal | Subject to restructuring; test against the MCP surface, not these constants directly. |
| `minions-viz/` HTTP + WebSocket API | experimental | Read-only observatory; endpoint paths and payload shapes may change in any patch. |
| `minions/tools/experiment_ssh.py` SSH execution | experimental | GPU queue API and scheduler internals stabilizing; breaking changes possible in patch releases. |
| `minions/review/` prompt assets and templates | experimental | Templates and personas are tuned per release; downstream consumers should pin a commit. |
| `minions/domains/*.md` domain packs | experimental | Content and format revised as new Expert domains are added. |
| `MANUAL/` reference docs | experimental | Fetch-on-demand reference; restructured between minor versions. |

<!-- INSERT_MORE -->

---

## Deprecation policy

1. **Announce.** A surface is marked `deprecated` in the table above and
   in the relevant docstring/prompt, and a `DeprecationWarning` (Python)
   or warning log line (MCP / CLI) is emitted on use.
2. **Alias.** The deprecated surface continues to function as an alias
   to its replacement for at least **one full minor release**.
3. **Remove.** Removal happens no earlier than the next minor bump after
   the alias was introduced. The CHANGELOG `### Removed` entry names the
   removed surface and links to the replacement.
4. **No silent breakage.** Stable surfaces never change semantics
   without going through the announce → alias → remove cycle.

## Breaking-change rules

A change is **breaking** if it can cause an existing caller's previously
working invocation to fail or to silently produce a different result.
Examples:

- Removing or renaming an `mos_*` MCP tool or any of its parameters.
- Changing the type or required-ness of an `mos_*` parameter.
- Removing or renaming a `MinionsError` subclass.
- Removing a `Role` (e.g. `Coder`, `Writer`) without a migration path.
- Removing or renaming a §-numbered section in `minions/roles/SYSTEM.md`.
- Changing the exit-code contract of a `mos` CLI subcommand.
- Changing the schema of `state/projects.json` without a forward-compatible
  reader.

Non-breaking (allowed in any release):

- Adding a new `mos_*` MCP tool.
- Adding a new optional parameter (with a default) to an existing tool.
- Adding a new `Role`, skill, or domain pack.
- Adding a new optional field to `MissionProfile` or `state/projects.json`.
- Adding a new exception subclass.
- Internal refactoring of `minions/lifecycle/*.py` that preserves MCP
  surface behavior.

## Versioning scheme

MinionsOS follows [SemVer](https://semver.org/) at the `pyproject.toml`
level (`major.minor.patch`). The `vX.Y` tags in commit messages are
**internal milestone tags** and do not, on their own, correspond to
pyproject version bumps. Pyproject version bumps occur at deliberate
release points and are tagged in git (e.g. `v0.5.3`).

## Out-of-scope (no stability claim)

- Any file under `.claude/`, `branches/`, `state/`, or `projects/` —
  these are runtime/workspace, not API.
- Anything inside `~/.claude/skills/` — global skills are tuned per
  install.
- Internal Pydantic model field names (only the MCP-serialized JSON is
  the contract).
- Log line wording. Treat logs as human-readable, not machine-parseable.

