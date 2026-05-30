//! Resolve where MinionsOS lives and discover Gru installs.
//!
//! READ side only — paths to state files. Writes always go through `mos`.

use anyhow::{Context, Result};
use serde::Deserialize;
use std::path::{Path, PathBuf};

/// One Gru install, from `~/.minionsos/grus.json`.
#[derive(Debug, Clone, Deserialize)]
pub struct GruEntry {
    pub id: String,
    #[serde(default)]
    pub label: String,
    pub root_path: PathBuf,
    #[serde(default)]
    pub parent_repo: Option<PathBuf>,
    pub state_dir: PathBuf,
    #[serde(default)]
    pub registered_at: Option<String>,
    #[serde(default)]
    pub last_seen: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
struct GruRegistry {
    #[serde(default)]
    grus: Vec<GruEntry>,
}

/// Path to `~/.minionsos/grus.json`.
pub fn registry_path() -> Option<PathBuf> {
    dirs::home_dir().map(|h| h.join(".minionsos").join("grus.json"))
}

/// Read every registered Gru install. Missing registry -> empty list.
pub fn read_registry() -> Result<Vec<GruEntry>> {
    let Some(p) = registry_path() else {
        return Ok(Vec::new());
    };
    if !p.exists() {
        return Ok(Vec::new());
    }
    let raw = std::fs::read_to_string(&p)
        .with_context(|| format!("reading registry {}", p.display()))?;
    let reg: GruRegistry =
        serde_json::from_str(&raw).with_context(|| format!("parsing {}", p.display()))?;
    Ok(reg.grus)
}

/// Where MinionsOS is rooted for the active session.
///
/// Resolution order: explicit override (`MINIONS_ROOT` env) -> the cwd if it
/// looks like a MinionsOS checkout -> the first registered Gru's `root_path`.
#[derive(Debug, Clone)]
pub struct GruContext {
    pub id: String,
    pub label: String,
    pub root: PathBuf,
    pub state_dir: PathBuf,
}

impl GruContext {
    pub fn projects_json(&self) -> PathBuf {
        // `MINIONS_PROJECTS_ROOT` can relocate projects/, but projects.json
        // always lives under the state dir.
        self.state_dir.join("projects.json")
    }

    /// `projects/` root. Honors `MINIONS_PROJECTS_ROOT`, else `<root>/projects`.
    pub fn projects_root(&self) -> PathBuf {
        if let Ok(p) = std::env::var("MINIONS_PROJECTS_ROOT") {
            return PathBuf::from(p);
        }
        self.root.join("projects")
    }

    pub fn project_dir(&self, port: u16) -> PathBuf {
        self.projects_root().join(format!("project_{port}"))
    }

    pub fn role_log(&self, port: u16, role: &str) -> PathBuf {
        self.project_dir(port)
            .join("logs")
            .join(format!("role-{role}.log"))
    }

    pub fn health_events(&self, port: u16) -> PathBuf {
        self.project_dir(port).join("logs").join("health_events.jsonl")
    }

    /// The `mos` launcher for this install, used for all write actions.
    pub fn mos_bin(&self) -> PathBuf {
        self.root.join("mos")
    }
}

fn looks_like_minions_root(p: &Path) -> bool {
    p.join("minions").join("state").join("projects.json").exists()
        || (p.join("mos").exists() && p.join("minions").is_dir())
}

/// Resolve the active Gru context from env + cwd + registry.
pub fn resolve_context(grus: &[GruEntry]) -> Result<GruContext> {
    if let Ok(root) = std::env::var("MINIONS_ROOT") {
        let root = PathBuf::from(root);
        return Ok(GruContext {
            id: "env".into(),
            label: "MINIONS_ROOT".into(),
            state_dir: root.join("minions").join("state"),
            root,
        });
    }
    if let Ok(cwd) = std::env::current_dir() {
        for cand in cwd.ancestors() {
            if looks_like_minions_root(cand) {
                return Ok(GruContext {
                    id: "cwd".into(),
                    label: "cwd".into(),
                    state_dir: cand.join("minions").join("state"),
                    root: cand.to_path_buf(),
                });
            }
        }
    }
    if let Some(g) = grus.first() {
        return Ok(context_from_entry(g));
    }
    anyhow::bail!(
        "Could not locate a MinionsOS install. Run from inside a checkout, \
         set MINIONS_ROOT, or register a Gru in ~/.minionsos/grus.json."
    )
}

pub fn context_from_entry(g: &GruEntry) -> GruContext {
    GruContext {
        id: g.id.clone(),
        label: g.label.clone(),
        root: g.root_path.clone(),
        state_dir: g.state_dir.clone(),
    }
}

