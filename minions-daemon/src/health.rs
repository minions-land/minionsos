use anyhow::Result;
use minions_core::{Project, StateStore};
use reqwest::Client;
use std::time::Duration;

/// Check if a backend is healthy via HTTP /health endpoint
pub async fn backend_health(client: &Client, port: u16) -> bool {
    let url = format!("http://127.0.0.1:{}/health", port);

    match client
        .get(&url)
        .timeout(Duration::from_secs(5))
        .send()
        .await
    {
        Ok(resp) if resp.status().is_success() => true,
        Ok(_) => false,
        Err(_) => false,
    }
}

/// Attempt to respawn a crashed backend by calling Python
pub async fn respawn_backend(port: u16) -> Result<()> {
    tracing::info!("Attempting to respawn backend on port {}", port);

    let output = tokio::process::Command::new("uv")
        .args(&["run", "python", "-m", "minions.lifecycle.project"])
        .args(&["respawn", &port.to_string()])
        .output()
        .await?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!("Backend respawn failed: {}", stderr);
    }

    tracing::info!("Backend respawned successfully on port {}", port);
    Ok(())
}

/// Check if a tmux session is alive
pub async fn tmux_session_alive(session_name: &str) -> bool {
    let output = tokio::process::Command::new("tmux")
        .args(&["list-sessions"])
        .output()
        .await;

    match output {
        Ok(out) => {
            let sessions = String::from_utf8_lossy(&out.stdout);
            sessions.lines().any(|line| line.starts_with(session_name))
        }
        Err(_) => false,
    }
}

/// Main health monitoring tick
pub async fn tick_health_monitor(
    client: &Client,
    store: &StateStore,
    crash_counter: &mut CrashCounter,
) -> Result<Vec<String>> {
    let mut events = Vec::new();
    let projects = store.load_projects()?;

    // Filter active projects
    let active: Vec<_> = projects
        .iter()
        .filter(|p| matches!(p.status, minions_core::ProjectStatus::Active))
        .collect();

    if active.is_empty() {
        tracing::info!("No active projects, health monitor idle");
        return Ok(events);
    }

    for project in active {
        let port = project.port;
        let healthy = backend_health(client, port).await;

        if !healthy {
            crash_counter.record_crash(port);

            if crash_counter.threshold_exceeded(port) {
                let msg = format!(
                    "[ALERT] Backend on port {} ({}) has crashed ≥3 times in 1h. \
                     Auto-restart disabled. Manual intervention required.",
                    port, project.real_name
                );
                tracing::error!("{}", msg);
                events.push(msg);
            } else {
                let msg = format!(
                    "[WARN] Backend on port {} ({}) is unhealthy. Attempting respawn...",
                    port, project.real_name
                );
                tracing::warn!("{}", msg);
                events.push(msg.clone());

                match respawn_backend(port).await {
                    Ok(_) => {
                        let success = format!("[INFO] Backend respawned on port {}", port);
                        tracing::info!("{}", success);
                        events.push(success);
                    }
                    Err(e) => {
                        let err = format!("[ERROR] Backend respawn failed on port {}: {}", port, e);
                        tracing::error!("{}", err);
                        events.push(err);
                    }
                }
            }
        } else {
            crash_counter.reset(port);
        }
    }

    Ok(events)
}

/// Simple crash counter (3 crashes in 1 hour threshold)
pub struct CrashCounter {
    crashes: std::collections::HashMap<u16, Vec<std::time::Instant>>,
}

impl CrashCounter {
    pub fn new() -> Self {
        Self {
            crashes: std::collections::HashMap::new(),
        }
    }

    pub fn record_crash(&mut self, port: u16) {
        let now = std::time::Instant::now();
        let entry = self.crashes.entry(port).or_insert_with(Vec::new);

        // Remove crashes older than 1 hour
        entry.retain(|&t| now.duration_since(t).as_secs() < 3600);
        entry.push(now);
    }

    pub fn threshold_exceeded(&self, port: u16) -> bool {
        self.crashes.get(&port).map_or(false, |v| v.len() >= 3)
    }

    pub fn reset(&mut self, port: u16) {
        self.crashes.remove(&port);
    }
}

impl Default for CrashCounter {
    fn default() -> Self {
        Self::new()
    }
}
