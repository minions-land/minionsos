//! Whole-Gru, memory-aware read-only context for the haiku chat box.
//!
//! The operator's haiku assistant isn't scoped to the one pane in view — it can
//! answer "who's doing what across the whole install" and "what does the
//! project memory say so far". This module assembles that picture from files
//! the TUI already reads safely:
//!
//!   * the live Snapshot (every project + role + task/blocked state),
//!   * the focused project's persistent memory layers — L1 Draft
//!     (`branches/shared/draft/draft.json`) and L2 Book
//!     (`branches/shared/book/{hot.md,index.md}`),
//!   * recent staged notes and governance signboard.
//!
//! Everything degrades gracefully: a missing file contributes nothing, never an
//! error. Strictly read-only — no EACN, no queue drain, no writes.

use crate::config::GruContext;
use crate::scanner::Snapshot;
use std::fmt::Write as _;
use std::path::PathBuf;

/// Cap on any single memory excerpt so one huge Draft can't blow the prompt.
const EXCERPT_CAP: usize = 2400;

/// The assembled context block injected into the haiku prompt.
pub struct Digest {
    /// One-line-per-project roster across the whole Gru install.
    pub roster: String,
    /// Memory excerpts for the focused project (may be empty).
    pub memory: String,
}

impl Digest {
    /// Render to the single `extra` string the haiku prompt expects.
    pub fn into_extra(self) -> String {
        let mut s = self.roster;
        if !self.memory.is_empty() {
            s.push('\n');
            s.push_str(&self.memory);
        }
        s
    }
}

/// Build the whole-install roster: every project, its phase, and each role's
/// live/stopped state + current task + blocked reason. This is the backbone of
/// "who's doing what" — independent of which pane the operator is looking at.
pub fn roster(snap: &Snapshot) -> String {
    if snap.projects.is_empty() {
        return "No projects are currently running in this Gru install.".to_string();
    }
    let mut s = String::new();
    let total = snap.projects.len();
    let active = snap.projects.iter().filter(|p| p.status == "active").count();
    let live_roles: usize = snap
        .projects
        .iter()
        .flat_map(|p| &p.roles)
        .filter(|r| r.alive)
        .count();
    let _ = writeln!(
        s,
        "Gru install: {total} projects ({active} active), {live_roles} live role sessions.\n"
    );
    for p in &snap.projects {
        let live = p.roles.iter().filter(|r| r.alive).count();
        let _ = writeln!(
            s,
            "● {port} {name}  [{status}{phase}]  {live}/{n} roles live",
            port = p.port,
            name = p.name,
            status = p.status,
            phase = p
                .phase
                .as_deref()
                .filter(|x| !x.is_empty())
                .map(|x| format!(" · {x}"))
                .unwrap_or_default(),
            live = live,
            n = p.roles.len(),
        );
        for r in &p.roles {
            let task = r.current_task.as_deref().unwrap_or("—");
            let blocked = r
                .blocked_reason
                .as_deref()
                .map(|b| format!("  ⚠ BLOCKED: {b}"))
                .unwrap_or_default();
            let _ = writeln!(
                s,
                "    {dot} {role:<12} {task}{blocked}",
                dot = if r.alive { "live " } else { "stopped" },
                role = r.name,
                task = trim_one_line(task, 100),
                blocked = blocked,
            );
        }
    }
    s
}

/// Read the focused project's persistent memory layers into a compact block.
/// Pulls the Book hot-cache (the rolling summary derived from the
/// Ethics-curated Book), the Book index (catalog of compiled knowledge), and a
/// Draft summary. All optional; a project with no memory yet yields an empty
/// string.
pub fn project_memory(ctx: &GruContext, port: u16) -> String {
    let shared = ctx.project_dir(port).join("branches").join("shared");
    let mut blocks: Vec<String> = Vec::new();

    // L2 Book — the curated durable knowledge. hot.md is the wake-injected
    // rolling cache; index.md is the catalog.
    if let Some(hot) = read_excerpt(shared.join("book").join("hot.md"), EXCERPT_CAP) {
        blocks.push(format!("[Book · hot cache]\n{hot}"));
    }
    if let Some(idx) = read_excerpt(shared.join("book").join("index.md"), 1200) {
        blocks.push(format!("[Book · index]\n{idx}"));
    }

    // L1 Draft — the live process graph. We summarize node count + any
    // pending_plan / open-question text rather than dumping the JSON.
    if let Some(draft) = summarize_draft(shared.join("draft").join("draft.json")) {
        blocks.push(draft);
    }

    // Governance signboard — phase-transition consensus, if present.
    if let Some(gov) = read_excerpt(shared.join("governance").join("signboard.json"), 600) {
        blocks.push(format!("[Governance · signboard]\n{gov}"));
    }

    if blocks.is_empty() {
        return String::new();
    }
    format!(
        "Persistent memory for project {port} (read-only):\n{}",
        blocks.join("\n\n")
    )
}

/// Summarize a Draft graph (`draft.json`) without dumping it: node count plus
/// the text of any pending-plan / open-question / decision nodes (the
/// high-signal bits a returning role reconstructs context from).
fn summarize_draft(path: PathBuf) -> Option<String> {
    let raw = std::fs::read_to_string(&path).ok()?;
    let v: serde_json::Value = serde_json::from_str(&raw).ok()?;
    let nodes = v.get("nodes").and_then(|n| n.as_array());
    let count = nodes.map(|n| n.len()).unwrap_or(0);
    let mut highlights: Vec<String> = Vec::new();
    if let Some(arr) = nodes {
        for n in arr {
            let kind = n.get("kind").and_then(|k| k.as_str()).unwrap_or("");
            if matches!(kind, "pending_plan" | "open_question" | "decision") {
                if let Some(txt) = n
                    .get("text")
                    .or_else(|| n.get("summary"))
                    .and_then(|t| t.as_str())
                {
                    highlights.push(format!("  - [{kind}] {}", trim_one_line(txt, 120)));
                }
            }
            if highlights.len() >= 8 {
                break;
            }
        }
    }
    let mut s = format!("[Draft · process graph] {count} nodes");
    if !highlights.is_empty() {
        s.push('\n');
        s.push_str(&highlights.join("\n"));
    }
    Some(s)
}

/// Build the full digest: whole-install roster + focused-project memory.
/// `focus_port` is the project the operator is currently inside (or None at the
/// top-level list, in which case only the roster is built).
pub fn build(ctx: &GruContext, snap: &Snapshot, focus_port: Option<u16>) -> Digest {
    let memory = focus_port.map(|p| project_memory(ctx, p)).unwrap_or_default();
    Digest {
        roster: roster(snap),
        memory,
    }
}

/// Read a text file and cap it to `max` chars (head-biased — memory caches put
/// the freshest summary first). Missing/empty file -> None.
fn read_excerpt(path: PathBuf, max: usize) -> Option<String> {
    let raw = std::fs::read_to_string(&path).ok()?;
    let t = raw.trim();
    if t.is_empty() {
        return None;
    }
    if t.chars().count() <= max {
        Some(t.to_string())
    } else {
        let head: String = t.chars().take(max).collect();
        Some(format!("{head}…"))
    }
}

/// Collapse whitespace/newlines into a single line and cap length.
fn trim_one_line(s: &str, max: usize) -> String {
    let flat: String = s.split_whitespace().collect::<Vec<_>>().join(" ");
    if flat.chars().count() <= max {
        flat
    } else {
        let h: String = flat.chars().take(max.saturating_sub(1)).collect();
        format!("{h}…")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scanner::{ProjectStatus, RoleStatus};

    fn role(name: &str, alive: bool, task: Option<&str>) -> RoleStatus {
        RoleStatus {
            name: name.into(),
            state: "active".into(),
            session_name: format!("mos-1-{name}"),
            alive,
            current_task: task.map(|s| s.into()),
            blocked_reason: None,
            last_seen: None,
        }
    }

    #[test]
    fn roster_empty_install_is_friendly() {
        let snap = Snapshot::default();
        assert!(roster(&snap).contains("No projects"));
    }

    #[test]
    fn roster_lists_projects_and_roles() {
        let snap = Snapshot {
            projects: vec![ProjectStatus {
                port: 41001,
                name: "attn-study".into(),
                status: "active".into(),
                phase: Some("experiment".into()),
                venue: None,
                roles: vec![role("expert", true, Some("run sweep")), role("ethics", false, None)],
            }],
            error: None,
        };
        let r = roster(&snap);
        assert!(r.contains("41001 attn-study"));
        assert!(r.contains("experiment"));
        assert!(r.contains("expert"));
        assert!(r.contains("run sweep"));
        assert!(r.contains("1/2 roles live"));
    }

    #[test]
    fn trim_one_line_flattens_and_caps() {
        assert_eq!(trim_one_line("a\n  b   c", 100), "a b c");
        assert_eq!(trim_one_line("abcdef", 4), "abc…");
    }
}
