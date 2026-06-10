use std::path::PathBuf;

/// Get MinionsOS root directory (MINIONS_ROOT or try to find it)
pub fn minions_root() -> PathBuf {
    if let Ok(dir) = std::env::var("MINIONS_ROOT") {
        PathBuf::from(dir)
    } else {
        // Try to find MinionsOS root by looking for minions/ package directory
        // Start from current exe location and walk up
        if let Ok(exe) = std::env::current_exe() {
            let mut path = exe.parent().unwrap_or_else(|| std::path::Path::new(".")).to_path_buf();

            // Walk up looking for minions/ directory (package marker)
            for _ in 0..10 {
                let candidate = path.join("minions");
                if candidate.join("__init__.py").exists() || candidate.join("cli.py").exists() {
                    return path;
                }
                if let Some(parent) = path.parent() {
                    path = parent.to_path_buf();
                } else {
                    break;
                }
            }
        }

        // Fallback: assume current directory is MinionsOS root
        std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
    }
}

/// Get MinionsOS package directory (minions/)
pub fn package_dir() -> PathBuf {
    minions_root().join("minions")
}

/// Get MinionsOS state directory (minions/state/)
pub fn state_dir() -> PathBuf {
    package_dir().join("state")
}

/// Get projects.json path
pub fn projects_json() -> PathBuf {
    state_dir().join("projects.json")
}

/// Get projects root directory (MINIONS_PROJECTS_ROOT or MinionsOS/projects/)
pub fn projects_root() -> PathBuf {
    if let Ok(dir) = std::env::var("MINIONS_PROJECTS_ROOT") {
        PathBuf::from(dir)
    } else {
        minions_root().join("projects")
    }
}

/// Get project directory for given port
pub fn project_dir(port: u16) -> PathBuf {
    projects_root().join(format!("project_{}", port))
}

/// Get project meta.json path
pub fn project_meta_json(port: u16) -> PathBuf {
    project_dir(port).join("meta.json")
}
