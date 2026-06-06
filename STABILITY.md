# API Stability Policy

MinionsOS uses a three-tier stability classification for all public surfaces.
Breaking changes to **stable** surfaces require a minor-version bump and a
release-note migration entry. **Experimental** surfaces may change in any
patch. **Internal** surfaces carry no support guarantee.

---

## Stability tiers

| Tier | Definition |
|---|---|
| **stable** | Semver-bound. Removals and incompatible changes require a minor-version bump and release-note migration entry. |
| **experimental** | Under active development. Interface may change in any patch release without prior notice. |
| **internal** | Implementation detail. No support guarantee across any release. |

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

## Breaking-change rules

A change is **breaking** if it can cause an existing caller's previously
working invocation to fail or to silently produce a different result.
Examples:

- Removing or renaming an `mos_*` MCP tool or any of its parameters.
- Changing the type or required-ness of an `mos_*` parameter.
- Removing or renaming a `MinionsError` subclass.
- Removing a current `Role` or changing its launch contract without a migration path.
- Removing or renaming a §-numbered section in `minions/roles/SYSTEM.md`.
- Changing the exit-code contract of a `mos` CLI subcommand.
- Changing the schema of `state/projects.json` without a forward-readable
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
level (`major.minor.patch`). The `vN` milestone tags used in commit
messages and `CHANGELOG.md` correspond **one-to-one** with the minor
version: milestone `vN` is package version `0.N.x`, and a `vN.M` polish
commit maps to `0.N.M`. So commit `v20` ⇒ pyproject `0.20.0`.

There is a single version source of truth: `pyproject.toml [project].version`.
`minions.__version__` reads it from installed package metadata
(`importlib.metadata`) rather than hard-coding it, so the two can never
drift. On a milestone bump, update `pyproject.toml` (and the literal
fallback in `minions/__init__.py`), then `uv sync`.

## Out-of-scope (no stability claim)

- Any file under `.claude/`, `branches/`, `state/`, or `projects/` —
  these are runtime/workspace, not API.
- Anything inside `~/.claude/skills/` — global skills are tuned per
  install.
- Internal Pydantic model field names (only the MCP-serialized JSON is
  the contract).
- Log line wording. Treat logs as human-readable, not machine-parseable.
