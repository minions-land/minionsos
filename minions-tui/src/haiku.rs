//! Transient, project-free haiku chat box.
//!
//! A small, fast Claude (`claude --print --model haiku`) the operator can
//! summon with `h` to ask anything about the current view — "summarize what's
//! happening", "who's doing what", "draft an issue about this". It is strictly
//! READ-ONLY: it receives a snapshot of the current context (which project /
//! role / live screen the operator is looking at) and returns plain text. It
//! never writes to project state, never files anything, never touches mos.

use crate::tmux;
use anyhow::{Context, Result};
use std::process::Command;

/// Locate the `claude` binary, mirroring ManageCode's discovery order.
fn claude_bin() -> String {
    if let Ok(p) = std::env::var("CLAUDE_BIN") {
        return p;
    }
    for cand in ["/opt/homebrew/bin/claude", "/usr/local/bin/claude"] {
        if std::path::Path::new(cand).exists() {
            return cand.to_string();
        }
    }
    if let Some(home) = dirs::home_dir() {
        for rel in [".claude/local/bin/claude", ".local/bin/claude"] {
            let p = home.join(rel);
            if p.exists() {
                return p.to_string_lossy().into_owned();
            }
        }
    }
    "claude".to_string()
}

/// A read-only snapshot of what the operator is currently looking at, fed to
/// haiku as grounding context. Built by the caller from App state.
#[derive(Debug, Clone, Default)]
pub struct AskContext {
    /// Human label of where we are, e.g. "project 41001 attention-sparsity-study, role expert".
    pub scope: String,
    /// Optional tmux session whose visible screen should be included verbatim.
    pub session: Option<String>,
    /// Optional extra lines (e.g. the project/role list the operator sees).
    pub extra: String,
}

fn build_prompt(ctx: &AskContext, question: &str) -> String {
    let mut screen = String::new();
    if let Some(sess) = &ctx.session {
        if let Ok(raw) = tmux::capture_screen(sess) {
            screen = format!("\n\nLive terminal of {sess}:\n```\n{}\n```", tail_chars(&raw, 4000));
        }
    }
    format!(
        "You are the operator's assistant embedded in the MinionsOS control-plane \
TUI. MinionsOS is a multi-agent OS: Gru supervises isolated projects, each \
running resident Role processes (Ethics and Expert instances) plus persistent \
memory layers (Reel, Draft, Book). You can see the WHOLE install below — every \
project, every role's live/stopped state and current task, and the focused \
project's memory. Use all of it to answer; you are not limited to one pane.\n\n\
The operator is currently looking at: {scope}.\n\n\
Answer concisely in plain text — no markdown headers or bold, just a few short \
lines or a tight bullet list. You are strictly READ-ONLY: you observe and \
advise, you never take actions. If asked to 'file an issue' or 'write an \
issue', just draft the text for the operator to copy; you cannot submit it.\n\n\
=== Current MinionsOS state (read-only) ===\n{extra}{screen}\n\n\
Operator question: {question}",
        scope = if ctx.scope.is_empty() { "the MinionsOS control plane" } else { &ctx.scope },
        extra = ctx.extra,
        screen = screen,
        question = question,
    )
}

/// Ask haiku a question with the given context. Blocking; returns plain text.
/// Project-free: spawns `claude --print --model haiku` and reads stdout.
/// Run this OFF the render thread (it can take a few seconds).
pub fn ask(ctx: &AskContext, question: &str) -> Result<String> {
    let prompt = build_prompt(ctx, question);
    let out = Command::new(claude_bin())
        .args([
            "--print",
            "--model",
            "haiku",
            "--permission-mode",
            "bypassPermissions",
        ])
        .arg(&prompt)
        .output()
        .context("spawning claude --print --model haiku")?;
    if !out.status.success() {
        anyhow::bail!("haiku failed: {}", String::from_utf8_lossy(&out.stderr).trim());
    }
    Ok(strip_markdown(String::from_utf8_lossy(&out.stdout).trim()))
}

/// Lightly de-markdown haiku output so the chat box reads as plain text:
/// drops `**bold**`/`__bold__` and leading `#` headers, keeps bullets. We don't
/// render markdown in the box, so literal `**` was showing through before.
fn strip_markdown(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for line in s.lines() {
        let trimmed = line.trim_start();
        // Drop ATX headers ("# ", "## "); keep the text after the hashes.
        let line = if let Some(rest) = trimmed.strip_prefix('#') {
            rest.trim_start_matches('#').trim_start()
        } else {
            line
        };
        out.push_str(&line.replace("**", "").replace("__", ""));
        out.push('\n');
    }
    out.trim_end().to_string()
}

fn tail_chars(s: &str, max: usize) -> String {
    let n = s.chars().count();
    if n <= max {
        return s.to_string();
    }
    s.chars().skip(n - max).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strip_markdown_removes_bold_and_headers() {
        assert_eq!(strip_markdown("**bold** text"), "bold text");
        assert_eq!(strip_markdown("## Heading"), "Heading");
        assert_eq!(strip_markdown("- a __b__ c"), "- a b c");
    }

    #[test]
    fn strip_markdown_preserves_plain_lines() {
        let s = "line one\nline two";
        assert_eq!(strip_markdown(s), s);
    }
}
