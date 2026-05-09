# Rust archive

This directory holds the Rust workspace that was briefly part of MinionsOS V5.
It is kept here as a historical reference and a possible future starting point;
nothing in the live runtime depends on it.

## Status

- Not built, not tested, not imported by any Python code.
- Not part of CI.
- Safe to delete entirely. Preserved so the V5 runtime-contracts experiment
  (`PhasePolicy`, `explicit_task_targets`) can be resurrected without a fresh
  greenfield if we ever restart the `mosd` work.

## What lived here

- `Cargo.toml`, `Cargo.lock` — workspace root.
- `crates/minions-runtime-core/` — one crate, one `lib.rs` (~310 lines),
  6 unit tests. Defines `RoleState`, `RoleRecord`, `PhasePolicy`,
  `TaskRecord`, `explicit_task_targets` as pure-function runtime contracts.
  The equivalent behaviour is implemented in Python at:
    - `minions/lifecycle/project.py:project_phase_allows_role`
    - `minions/lifecycle/project.py:project_phase_online_role_names`
    - `minions/lifecycle/wake_signals.py:task_explicit_targets`

## If you ever want to bring it back

```bash
git mv other/rust-archive/Cargo.toml .
git mv other/rust-archive/Cargo.lock .
git mv other/rust-archive/crates ./crates
```

Then restore the `# Rust` block in `.gitignore` and the `cargo` references in
`AGENTS.md`, `minions/CLAUDE.md`, and the root `CLAUDE.md`.

See `docs/rust_proposal/minionsos_v5_proposal.md` for the original design
intent (`mosd`, Rust adapter, Rust TUI).
