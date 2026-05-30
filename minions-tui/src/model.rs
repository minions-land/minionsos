//! Read-only deserialization of MinionsOS state files.
//!
//! Mirrors `minions/state/store.py` ProjectsData/ProjectEntry/RoleEntry, but
//! only the fields the TUI renders. `#[serde(default)]` everywhere so a schema
//! drift on the Python side never crashes the reader.

use serde::Deserialize;

#[derive(Debug, Clone, Default, Deserialize)]
pub struct ProjectsData {
    #[serde(default)]
    pub projects: Vec<ProjectEntry>,
    #[serde(default)]
    pub retired_ports: Vec<u16>,
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct ProjectEntry {
    pub port: u16,
    #[serde(default)]
    pub real_name: String,
    #[serde(default)]
    pub status: String, // active | dormant | closed
    #[serde(default)]
    pub created: Option<String>,
    #[serde(default)]
    pub venue: Option<String>,
    #[serde(default)]
    pub current_phase: Option<String>,
    #[serde(default)]
    pub phase_reason: Option<String>,
    #[serde(default)]
    pub active_roles: Vec<RoleEntry>,
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct RoleEntry {
    pub name: String,
    #[serde(default)]
    pub state: String, // active | sleeping | dismissed
    #[serde(default)]
    pub pid: Option<u32>,
    #[serde(default)]
    pub spawned_at: Option<String>,
    #[serde(default)]
    pub session_name: Option<String>,
    #[serde(default)]
    pub last_seen: Option<String>,
    #[serde(default)]
    pub current_task: Option<String>,
    #[serde(default)]
    pub blocked_reason: Option<String>,
}

impl ProjectEntry {
    pub fn is_active(&self) -> bool {
        self.status == "active"
    }
    pub fn display_name(&self) -> &str {
        if self.real_name.is_empty() {
            "(unnamed)"
        } else {
            &self.real_name
        }
    }
}
