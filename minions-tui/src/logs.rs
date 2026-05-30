//! Read-only log + health views. Tails per-role logs and the project's
//! health_events.jsonl without following (one-shot reads on a cadence).

use crate::config::GruContext;
use std::io::{Read, Seek, SeekFrom};

/// Tail the last `max_bytes` of a role's log file, returning decoded text.
/// Returns an empty string if the file is missing.
pub fn tail_role_log(ctx: &GruContext, port: u16, role: &str, max_bytes: u64) -> String {
    let path = ctx.role_log(port, role);
    tail_file(&path, max_bytes)
}

/// Read recent health events for a project, newest first, up to `limit` lines.
/// Each line is a JSON object; we surface a compact rendering.
pub fn recent_health(ctx: &GruContext, port: u16, limit: usize) -> Vec<HealthEvent> {
    let path = ctx.health_events(port);
    let raw = tail_file(&path, 64 * 1024);
    let mut events: Vec<HealthEvent> = raw
        .lines()
        .filter_map(|l| serde_json::from_str::<HealthEvent>(l).ok())
        .collect();
    events.reverse();
    events.truncate(limit);
    events
}

/// One health-event line from health_events.jsonl.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct HealthEvent {
    #[serde(default)]
    pub ts: String,
    #[serde(default)]
    pub kind: String,
    #[serde(default)]
    pub severity: String,
    #[serde(default)]
    pub message: String,
    #[serde(default)]
    pub role_name: Option<String>,
}

/// Read the last `max_bytes` bytes of a file as lossy UTF-8. Missing -> "".
fn tail_file(path: &std::path::Path, max_bytes: u64) -> String {
    let Ok(mut f) = std::fs::File::open(path) else {
        return String::new();
    };
    let len = f.metadata().map(|m| m.len()).unwrap_or(0);
    let start = len.saturating_sub(max_bytes);
    if f.seek(SeekFrom::Start(start)).is_err() {
        return String::new();
    }
    let mut buf = Vec::new();
    if f.read_to_end(&mut buf).is_err() {
        return String::new();
    }
    // Drop a partial first line when we seeked into the middle of the file.
    let text = String::from_utf8_lossy(&buf).into_owned();
    if start > 0 {
        if let Some(nl) = text.find('\n') {
            return text[nl + 1..].to_string();
        }
    }
    text
}
