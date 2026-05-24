# 01 — Lifecycle (Gru only)

> **L2 card.** This chapter is for Gru. Other roles: skip unless you're triaging a Gru log.
> Top three you'll use most: `mos_project_create`, `mos_spawn_expert`, `mos_project_set_phase`.
> Signboard tools (`mos_signboard_*`) live at the end — those ARE callable by every EACN role.

---

## mos_project_create

Spawn a new project on a free port.

```python
args:
  topic_doc: str         # absolute path to the MANDATE / topic spec
  real_name: str         # short slug used in directory names
  profile: str = "scientific-paper"  # or "hle-answer", or any minions/profiles/*.yaml
  upstream_branch: str = "HEAD"
  venue: str | None = None
  github_push_target: str | None = None
returns: { port, root, profile_summary, ... }
```

**Pitfalls.** The author seed repo (the parent of this MinionsOS clone) must be git-init'd. Files larger than 500 MB are skipped at import.

**Real example (project_37596):** `profile=scientific-paper`, `topic_doc=/root/autodl-tmp/Grokking/PROJECT-V2-prep/MANDATE.md`, `real_name=grokking-critical-norm-v2` → port 37596, four roles spawned (gru/noter/coder/ethics), Experts added later via `mos_spawn_expert`.

---

## mos_project_list

```python
args: {}
returns: list of { port, real_name, status, profile, roles_active, ... }
```
Use this before any cross-project op. Status ∈ {`active`, `dormant`, `closed`, `killed`}.

---

## mos_project_dormant / mos_project_revive / mos_project_close / mos_project_kill

| Tool | What | Reversible? |
|---|---|---|
| `_dormant` | tmux sessions stopped, EACN backend stopped, git/state preserved | yes — `_revive` |
| `_revive` | reopen backend, respawn role tmux sessions | n/a |
| `_close` | mark closed, retain artifacts; cannot be revived | no |
| `_kill` | hard SIGKILL the process tree | yes (data preserved) |

`project_37596` is currently `dormant`. To inspect it without waking, SSH and `cat`/`grep` its files directly — don't `_revive` just to look.

---

## mos_project_set_phase

```python
args:
  port: int
  phase: str        # e.g. "P1", "P2", "P3", or profile-defined
  reason: str       # required free-text rationale
  allowed_roles: list[str] | None = None  # optional gating
returns: { phase, phase_version, phase_reason, phase_updated_at }
```

The `phase_reason` field gets persisted in `meta.json` and is the single source of truth for "why are we in this phase". Make it a paragraph, not a word — `project_37596` example:
```
P1 verification consensus-complete: 3 signs raised (ethics + expert-mathematician
+ expert-dl-arch); ethics re-audit eeb5b8c confirms all 7 P1 gates PASS.
Advancing to P2 experiment phase per project lead authorization.
```

---

## mos_project_checkpoint_workspace

Snapshot all role worktrees + shared into a tag. Cheap. Run before any risky bulk operation (queue rebuild, mass publish, signboard reset).

---

## mos_spawn_role

Spawn a fixed-name role: `noter`, `coder`, `ethics`, `writer`.

```python
args:
  port: int
  role: str          # fixed names only
  config: dict | None
returns: { role, session_name, agent_id }
```
**Don't** use this for experts — use `mos_spawn_expert`.

---

## mos_spawn_expert

```python
args:
  port: int
  name: str          # the slug ONLY, e.g. "theory-normalization"
  domain: str | None # path to a minions/domains/*.md pack
  config: dict | None
returns: { role, session_name, agent_id, registered_role_name }
```

**Critical (see PITFALLS § P-2):** `name` is the slug, NOT `<slug>-expert`. The launcher prepends `expert-` for you. Pass `name="theory-normalization"`, get role `expert-theory-normalization`.

---

## mos_dismiss_role

Retire a role. Branch + audit log preserved. EACN agent unregistered.

```python
args:
  port: int
  role: str          # full registered role name (e.g. "expert-theory-normalization")
  reason: str
  preserve_branch: bool = True
```

---

## mos_list_roles / mos_kill_role / mos_attach_role

- `_list_roles` — what's running.
- `_kill_role` — hard kill the tmux session for a role; the watchdog respawns it.
- `_attach_role` — returns a `tmux attach` command for human eyeballs.

---

## Signboard (callable by all EACN roles)

The signboard is the project's phase-transition consensus board. Anyone can raise; Gru consumes.

### mos_signboard_set
```python
args:
  port: int
  topic: str            # what the sign is about (e.g. "advance-to-P2")
  position: str         # "support" | "oppose" | "neutral"
  rationale: str
  evidence_refs: list[str]
returns: { sign_id, signboard_state }
```
Persists to `branches/shared/governance/signboard.json`.

### mos_signboard_read / mos_signboard_evaluate
- `_read` — see all open signs and positions.
- `_evaluate` — compute consensus; returns `{verdict, support, oppose, neutral, decisive_evidence}`.

### mos_signboard_consume / mos_signboard_reopen (Gru only)
After acting on a sign, `_consume` archives it. `_reopen` brings it back if the action was reverted.

---

## mos_list_workflow_plugins

Lists plugins that can be spawned as Experts on this project (third-party EACN-callable agents brought in via the workflow plugin architecture).
