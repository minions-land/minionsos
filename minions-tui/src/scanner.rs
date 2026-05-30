//! Read MinionsOS state from disk + cheap tmux liveness.
//!
//! All reads are non-destructive: state files + `tmux has-session`. Never
//! touches EACN queues. Snapshots are produced for the render loop over mpsc.

use crate::config::GruContext;
use crate::model::ProjectsData;
use crate::tmux;
use anyhow::{Context, Result};

/// A role row enriched with live status the JSON file can't know.
#[derive(Debug, Clone)]
pub struct RoleStatus {
    pub name: String,
    pub state: String,
    pub session_name: String,
    pub alive: bool,
    pub current_task: Option<String>,
    pub blocked_reason: Option<String>,
    pub last_seen: Option<String>,
}

/// A project enriched with live role statuses.
#[derive(Debug, Clone)]
pub struct ProjectStatus {
    pub port: u16,
    pub name: String,
    pub status: String,
    pub phase: Option<String>,
    pub venue: Option<String>,
    pub roles: Vec<RoleStatus>,
}

/// Full read-side snapshot delivered to the UI thread.
#[derive(Debug, Clone, Default)]
pub struct Snapshot {
    pub projects: Vec<ProjectStatus>,
    pub error: Option<String>,
}

/// Parse projects.json for the active Gru. Missing file -> empty.
pub fn read_projects(ctx: &GruContext) -> Result<ProjectsData> {
    let p = ctx.projects_json();
    if !p.exists() {
        return Ok(ProjectsData::default());
    }
    let raw = std::fs::read_to_string(&p)
        .with_context(|| format!("reading {}", p.display()))?;
    let data: ProjectsData =
        serde_json::from_str(&raw).with_context(|| format!("parsing {}", p.display()))?;
    Ok(data)
}

/// Build a full snapshot: read state, then probe tmux liveness per role.
pub fn scan(ctx: &GruContext) -> Snapshot {
    let data = match read_projects(ctx) {
        Ok(d) => d,
        Err(e) => {
            return Snapshot {
                projects: Vec::new(),
                error: Some(format!("{e:#}")),
            }
        }
    };

    // One `tmux ls` to learn every live session, then membership-test per role
    // instead of forking has-session per role (240 projects * N roles).
    let live = tmux::list_sessions().unwrap_or_default();

    let mut projects = Vec::with_capacity(data.projects.len());

    for p in &data.projects {
        let mut roles = Vec::with_capacity(p.active_roles.len());
        for r in &p.active_roles {
            let sess = r
                .session_name
                .clone()
                .unwrap_or_else(|| tmux::session_name(p.port, &r.name));
            roles.push(RoleStatus {
                name: r.name.clone(),
                state: r.state.clone(),
                alive: live.contains(&sess),
                session_name: sess,
                current_task: r.current_task.clone(),
                blocked_reason: r.blocked_reason.clone(),
                last_seen: r.last_seen.clone(),
            });
        }
        projects.push(ProjectStatus {
            port: p.port,
            name: p.display_name().to_string(),
            status: p.status.clone(),
            phase: p.current_phase.clone(),
            venue: p.venue.clone(),
            roles,
        });
    }
    Snapshot {
        projects,
        error: None,
    }
}
