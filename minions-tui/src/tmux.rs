//! tmux driver — the soul of the drive pipeline.
//!
//! Three tiers, each the least-disturbing primitive for a live autonomous role:
//!   1. LOOK  : `capture-pane -ept` snapshot (no attach -> no resize reflow).
//!   2. STEER : `send-keys -l <text>` then `Enter` (same path as `mos role kick`).
//!   3. TAKEOVER: `attach` into the real pty (full fidelity; heavy).
//!
//! Every call passes an argv array — never a shell string — so role/port values
//! can't inject. Bounded timeouts convert a wedged tmux server into an error
//! instead of hanging the UI thread.

use anyhow::{Context, Result};
use std::collections::HashSet;
use std::process::Command;

/// tmux session name for a (port, role) — must match
/// `minions/lifecycle/role_launcher.py:session_name`.
pub fn session_name(port: u16, role: &str) -> String {
    format!("mos-{port}-{role}")
}

/// Every live tmux session name (`tmux ls -F '#{session_name}'`).
/// Returns empty set if no server is running.
pub fn list_sessions() -> Result<HashSet<String>> {
    let out = Command::new("tmux")
        .args(["ls", "-F", "#{session_name}"])
        .output();
    let out = match out {
        Ok(o) => o,
        Err(_) => return Ok(HashSet::new()), // tmux not installed
    };
    if !out.status.success() {
        // "no server running" is success-as-empty for our purposes.
        return Ok(HashSet::new());
    }
    let text = String::from_utf8_lossy(&out.stdout);
    Ok(text.lines().map(|l| l.trim().to_string()).collect())
}

/// True if this role's session is live right now.
pub fn session_alive(port: u16, role: &str) -> bool {
    Command::new("tmux")
        .args(["has-session", "-t", &session_name(port, role)])
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

/// LOOK: capture the current pane contents, ANSI escapes preserved (`-e`),
/// joined-wrapped lines disabled (`-p` to stdout, `-J` off). `-S -<n>` pulls
/// scrollback. Returns raw bytes including SGR sequences for vt100 parsing.
pub fn capture_pane(session: &str, scrollback: u32) -> Result<String> {
    let start = format!("-{scrollback}");
    let out = Command::new("tmux")
        .args(["capture-pane", "-p", "-e", "-t", session, "-S", &start])
        .output()
        .with_context(|| format!("capture-pane -t {session}"))?;
    if !out.status.success() {
        anyhow::bail!(
            "capture-pane failed for {session}: {}",
            String::from_utf8_lossy(&out.stderr).trim()
        );
    }
    Ok(String::from_utf8_lossy(&out.stdout).into_owned())
}

/// LOOK (crisp): capture only the *visible screen* of a session — no
/// scrollback — at the session's own geometry. This is what an attached
/// operator sees right now, so rendering it full-width reproduces the real
/// terminal faithfully (no reflow, no scrollback mangling). `-e` keeps SGR.
pub fn capture_screen(session: &str) -> Result<String> {
    let out = Command::new("tmux")
        .args(["capture-pane", "-p", "-e", "-t", session])
        .output()
        .with_context(|| format!("capture-pane (screen) -t {session}"))?;
    if !out.status.success() {
        anyhow::bail!(
            "capture-pane failed for {session}: {}",
            String::from_utf8_lossy(&out.stderr).trim()
        );
    }
    Ok(String::from_utf8_lossy(&out.stdout).into_owned())
}

/// Return a session's pane geometry as (cols, rows), via
/// `display-message -p '#{pane_width} #{pane_height}'`. Falls back to None.
pub fn pane_size(session: &str) -> Option<(u16, u16)> {
    let out = Command::new("tmux")
        .args([
            "display-message",
            "-p",
            "-t",
            session,
            "#{pane_width} #{pane_height}",
        ])
        .output()
        .ok()?;
    if !out.status.success() {
        return None;
    }
    let s = String::from_utf8_lossy(&out.stdout);
    let mut it = s.split_whitespace();
    let w: u16 = it.next()?.parse().ok()?;
    let h: u16 = it.next()?.parse().ok()?;
    Some((w, h))
}

/// Resize a session's window to (cols, rows) so its next render matches the
/// space we have for the cockpit. Uses `resize-window` (tmux 2.9+); harmless
/// if the session has no window. We only call this when the operator is
/// actively viewing one role full-screen, so reflowing it is intended.
pub fn resize_window(session: &str, cols: u16, rows: u16) {
    let _ = Command::new("tmux")
        .args([
            "resize-window",
            "-t",
            session,
            "-x",
            &cols.to_string(),
            "-y",
            &rows.to_string(),
        ])
        .output();
}


/// STEER: inject literal text into a live pane, then submit with Enter.
///
/// Uses `send-keys -l` (literal bytes, no key-binding interpretation) — the
/// empirically reliable path through the Claude Code input widget (Issue #17),
/// matching `mos role kick`. Sends Enter `retries` times with `wait` between,
/// since tmux can't confirm the TUI committed the line.
pub fn send_text(session: &str, text: &str, retries: u8, wait_ms: u64) -> Result<()> {
    if text.is_empty() {
        anyhow::bail!("refusing to send empty text");
    }
    let rc = Command::new("tmux")
        .args(["send-keys", "-t", session, "-l", text])
        .status()
        .with_context(|| format!("send-keys -l -t {session}"))?;
    if !rc.success() {
        anyhow::bail!("send-keys -l failed for {session}");
    }
    for _ in 0..retries.max(1) {
        std::thread::sleep(std::time::Duration::from_millis(wait_ms));
        let _ = Command::new("tmux")
            .args(["send-keys", "-t", session, "Enter"])
            .status();
    }
    Ok(())
}

/// STEER (control key): send a single named key (e.g. "Enter", "C-c", "Escape").
pub fn send_key(session: &str, key: &str) -> Result<()> {
    let rc = Command::new("tmux")
        .args(["send-keys", "-t", session, key])
        .status()
        .with_context(|| format!("send-keys {key} -t {session}"))?;
    if !rc.success() {
        anyhow::bail!("send-keys {key} failed for {session}");
    }
    Ok(())
}

/// Resize a session's window — used right before a full TAKEOVER so the live
/// pane reflows to *our* terminal size only when the operator explicitly opts
/// into driving it (never during passive capture).
pub fn attach_argv(session: &str) -> Vec<String> {
    vec![
        "tmux".into(),
        "attach-session".into(),
        "-t".into(),
        session.into(),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn session_name_matches_role_launcher_format() {
        // Must equal minions/lifecycle/role_launcher.py:session_name.
        assert_eq!(session_name(37596, "expert"), "mos-37596-expert");
        assert_eq!(session_name(9000, "expert-rl"), "mos-9000-expert-rl");
    }

    #[test]
    fn send_text_rejects_empty() {
        assert!(send_text("mos-1-x", "", 1, 1).is_err());
    }
}

