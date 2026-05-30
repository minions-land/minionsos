//! Write actions — every mutation shells out to `mos`, never touches state
//! files or EACN directly. This reuses the CLI's authorization and its
//! destructive-action guardrails (e.g. `--i-know-this-kills-autonomy`).
//!
//! Returns the captured stdout/stderr so the UI can surface the result.

use crate::config::GruContext;
use anyhow::{Context, Result};
use std::process::Command;

/// Result of a `mos` invocation.
#[derive(Debug, Clone)]
pub struct CmdOutput {
    pub ok: bool,
    pub code: i32,
    pub stdout: String,
    pub stderr: String,
}

fn run_mos(ctx: &GruContext, args: &[&str]) -> Result<CmdOutput> {
    let mos = ctx.mos_bin();
    let out = Command::new(&mos)
        .args(args)
        .current_dir(&ctx.root)
        .output()
        .with_context(|| format!("running {} {:?}", mos.display(), args))?;
    Ok(CmdOutput {
        ok: out.status.success(),
        code: out.status.code().unwrap_or(-1),
        stdout: String::from_utf8_lossy(&out.stdout).into_owned(),
        stderr: String::from_utf8_lossy(&out.stderr).into_owned(),
    })
}

// ---- Role write actions (map 1:1 to `mos role <verb>`) -------------------

/// STEER nudge: `mos role kick PORT NAME --prompt <text>`.
pub fn role_kick(ctx: &GruContext, port: u16, role: &str, prompt: &str) -> Result<CmdOutput> {
    let port_s = port.to_string();
    run_mos(ctx, &["role", "kick", &port_s, role, "--prompt", prompt])
}

/// Dismiss a role: `mos role dismiss PORT NAME`.
pub fn role_dismiss(ctx: &GruContext, port: u16, role: &str) -> Result<CmdOutput> {
    let port_s = port.to_string();
    run_mos(ctx, &["role", "dismiss", &port_s, role])
}

/// List roles as JSON: `mos role list PORT --json`.
pub fn role_list_json(ctx: &GruContext, port: u16) -> Result<CmdOutput> {
    let port_s = port.to_string();
    run_mos(ctx, &["role", "list", &port_s, "--json"])
}

// ---- Project + status (read-via-CLI helpers) -----------------------------

/// `mos status --json` — authoritative dashboard the CLI already computes.
pub fn status_json(ctx: &GruContext) -> Result<CmdOutput> {
    run_mos(ctx, &["status", "--json"])
}

/// `mos project list --json`.
pub fn project_list_json(ctx: &GruContext) -> Result<CmdOutput> {
    run_mos(ctx, &["project", "list", "--json"])
}

// ---- Config (settings panel) ---------------------------------------------

/// `mos config --json` — full runtime config snapshot (includes the
/// context-pressure tunables the settings panel edits).
pub fn config_json(ctx: &GruContext) -> Result<CmdOutput> {
    run_mos(ctx, &["config", "--json"])
}

/// `mos config set KEY VALUE --json` — write one scalar tunable to gru.yaml.
/// The CLI enforces the allowlist + the medium<high invariant, so the TUI
/// never has to replicate that logic; it just surfaces the result.
pub fn config_set(ctx: &GruContext, key: &str, value: &str) -> Result<CmdOutput> {
    run_mos(ctx, &["config", "set", key, value, "--json"])
}

// ---- The argv for a full TAKEOVER, run via suspend-then-exec -------------

/// `mos role drive PORT NAME --i-know-this-kills-autonomy` — the heavy
/// takeover. The caller must suspend the TUI first (this BLOCKS, owning the
/// terminal). The CLI itself enforces the autonomy-kill acknowledgement, so
/// the operator sees the same guardrail as on the command line.
pub fn drive_argv(ctx: &GruContext, port: u16, role: &str) -> Vec<String> {
    vec![
        ctx.mos_bin().to_string_lossy().into_owned(),
        "role".into(),
        "drive".into(),
        port.to_string(),
        role.into(),
        "--i-know-this-kills-autonomy".into(),
    ]
}

/// `mos role attach PORT NAME` — read-mostly live attach (Ctrl-b d to detach).
/// Also suspend-then-exec; does NOT kill the session.
pub fn attach_argv(ctx: &GruContext, port: u16, role: &str) -> Vec<String> {
    vec![
        ctx.mos_bin().to_string_lossy().into_owned(),
        "role".into(),
        "attach".into(),
        port.to_string(),
        role.into(),
    ]
}

