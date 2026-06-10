use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;

use crate::paths;

/// Project status enum matching Python's ProjectStatus
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum ProjectStatus {
    Active,
    Dormant,
    Closed,
}

/// Role state enum
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum RoleState {
    Active,
    Idle,
    Dismissed,
}

/// Role information from active_roles array
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RoleInfo {
    pub name: String,
    pub state: RoleState,
    pub pid: Option<u32>,
    pub spawned_at: Option<DateTime<Utc>>,
    pub session_name: String,
    #[serde(default)]
    pub session_resumable: bool,
    pub workspace_path: Option<String>,
    pub workspace_branch: Option<String>,
    pub eacn_agent_id: Option<String>,
    pub last_seen: Option<DateTime<Utc>>,
    pub current_task: Option<String>,
    pub blocked_reason: Option<String>,
}

/// Project record from projects.json
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Project {
    pub port: u16,
    pub real_name: String,
    pub status: ProjectStatus,
    pub created: DateTime<Utc>,
    pub dormant_at: Option<DateTime<Utc>>,
    pub closed_at: Option<DateTime<Utc>>,
    pub venue: Option<String>,
    pub upstream_branch: String,
    pub current_branch: String,
    pub workspace_root: Option<String>,
    pub workspace_main: Option<String>,
    pub workspace_roles_root: Option<String>,
    pub workspace_shared: Option<String>,
    pub github_push_target: Option<String>,
    pub github_push_branch_prefix: Option<String>,
    pub current_phase: Option<String>,
    pub phase_version: u32,
    pub phase_allowed_roles: Vec<String>,
    pub phase_updated_at: Option<DateTime<Utc>>,
    pub phase_reason: Option<String>,
    pub active_roles: Vec<RoleInfo>,
}

/// projects.json root structure
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProjectsRoot {
    pub projects: Vec<Project>,
}

/// Project metadata from meta.json (extended fields)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProjectMeta {
    pub port: u16,
    pub real_name: String,
    pub status: ProjectStatus,
    pub created: DateTime<Utc>,
    pub dormant_at: Option<DateTime<Utc>>,
    pub closed_at: Option<DateTime<Utc>>,
    pub active_roles: Vec<RoleInfo>,
    pub backend_pid: Option<u32>,
    pub profile: Option<String>,
    pub venue: Option<String>,
    #[serde(default)]
    pub eacn_agent_map: HashMap<String, serde_json::Value>,
    // Additional fields omitted for now, add as needed
}

/// State store for reading MinionsOS state files
pub struct StateStore {
    projects_json_path: PathBuf,
}

impl StateStore {
    /// Create a new StateStore using default paths
    pub fn new() -> Self {
        Self {
            projects_json_path: paths::projects_json(),
        }
    }

    /// Create a StateStore with custom projects.json path
    pub fn with_path(path: PathBuf) -> Self {
        Self {
            projects_json_path: path,
        }
    }

    /// Load all projects from projects.json
    pub fn load_projects(&self) -> Result<Vec<Project>> {
        let contents = fs::read_to_string(&self.projects_json_path)
            .context("Failed to read projects.json")?;

        let root: ProjectsRoot = serde_json::from_str(&contents)
            .context("Failed to parse projects.json")?;

        Ok(root.projects)
    }

    /// Load a single project by port
    pub fn load_project(&self, port: u16) -> Result<Option<Project>> {
        let projects = self.load_projects()?;
        Ok(projects.into_iter().find(|p| p.port == port))
    }

    /// Load project metadata from meta.json
    pub fn load_project_meta(&self, port: u16) -> Result<ProjectMeta> {
        let meta_path = paths::project_meta_json(port);
        let contents = fs::read_to_string(&meta_path)
            .with_context(|| format!("Failed to read meta.json for port {}", port))?;

        let meta: ProjectMeta = serde_json::from_str(&contents)
            .with_context(|| format!("Failed to parse meta.json for port {}", port))?;

        Ok(meta)
    }

    /// List all project ports
    pub fn list_ports(&self) -> Result<Vec<u16>> {
        let projects = self.load_projects()?;
        Ok(projects.into_iter().map(|p| p.port).collect())
    }

    /// Check if projects.json exists
    pub fn exists(&self) -> bool {
        self.projects_json_path.exists()
    }
}

impl Default for StateStore {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    #[test]
    fn test_parse_real_projects_json() {
        // Try to read actual projects.json from MinionsOS state
        let state_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .join("minions/state/projects.json");

        if !state_path.exists() {
            eprintln!("Skipping test: projects.json not found at {:?}", state_path);
            return;
        }

        let store = StateStore::with_path(state_path);
        let projects = store.load_projects();

        match projects {
            Ok(projects) => {
                println!("Successfully loaded {} projects", projects.len());
                for p in &projects {
                    println!("  - {} (port {}, status: {:?})", p.real_name, p.port, p.status);
                }
                assert!(!projects.is_empty(), "Expected at least one project");
            }
            Err(e) => {
                eprintln!("Failed to load projects: {}", e);
                panic!("projects.json parsing failed");
            }
        }
    }
}
