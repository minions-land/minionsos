//! Wrap Gru itself into the TUI.
//!
//! Gru is just another long-lived `claude` process — today the `./gru`
//! launcher execs it in the foreground. To make "open TUI = Gru", we ensure a
//! tmux session named `mos-gru` running `./gru`, then surface Gru as a
//! first-class cockpit target so the same capture-pane + send-keys pipeline
//! that drives roles also drives Gru. We do NOT fork the launcher's logic; we
//! run it verbatim inside tmux.

use crate::config::GruContext;
use crate::tmux;
use anyhow::{Context, Result};
use std::process::Command;

/// The tmux session name that hosts the Gru process. Distinct from the
/// `mos-{port}-{role}` role namespace so it never collides with a project role.
pub const GRU_SESSION: &str = "mos-gru";

/// Is the Gru session live right now?
pub fn gru_alive() -> bool {
    Command::new("tmux")
        .args(["has-session", "-t", GRU_SESSION])
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

/// Ensure a `mos-gru` tmux session exists, launching `./gru` inside it if not.
/// Idempotent: a no-op when the session already exists. Returns true if it had
/// to start a new session.
pub fn ensure_gru(ctx: &GruContext) -> Result<bool> {
    if gru_alive() {
        return Ok(false);
    }
    let launcher = ctx.root.join("gru");
    if !launcher.exists() {
        anyhow::bail!("gru launcher not found at {}", launcher.display());
    }
    // Detached session running the real launcher in the repo root. The
    // launcher exports MINIONS_ROOT, starts the monitor sidecar, and execs
    // the Claude/Codex Gru host — exactly as a manual `./gru` would.
    let status = Command::new("tmux")
        .args([
            "new-session",
            "-d",
            "-s",
            GRU_SESSION,
            "-c",
            &ctx.root.to_string_lossy(),
            &launcher.to_string_lossy(),
        ])
        .status()
        .context("tmux new-session for Gru")?;
    if !status.success() {
        anyhow::bail!("tmux new-session failed for {GRU_SESSION}");
    }
    Ok(true)
}

/// Capture the Gru pane (same primitive used for roles).
pub fn capture(scrollback: u32) -> Result<String> {
    tmux::capture_pane(GRU_SESSION, scrollback)
}

/// The argv to attach to the Gru session full-screen (suspend-then-exec).
pub fn attach_argv() -> Vec<String> {
    tmux::attach_argv(GRU_SESSION)
}
