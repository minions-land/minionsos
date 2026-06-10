use serde::Deserialize;
use std::path::PathBuf;

/// Gru daemon configuration (maps to gru.yaml)
#[derive(Debug, Clone, Deserialize)]
pub struct DaemonConfig {
    /// Heartbeat interval in seconds
    #[serde(default = "default_heartbeat_interval")]
    pub heartbeat_interval_seconds: u64,

    /// Experiment reconcile interval
    #[serde(default = "default_experiment_interval")]
    pub experiment_reconcile_interval_seconds: u64,

    /// Role evolution interval
    #[serde(default = "default_role_evolution_interval")]
    pub role_evolution_interval_seconds: u64,

    /// Auto-apply role evolution recommendations
    #[serde(default)]
    pub role_evolution_auto_apply: bool,

    /// Enable Gru drive
    #[serde(default)]
    pub gru_drive_enabled: bool,

    /// Gru drive interval
    #[serde(default = "default_gru_drive_interval")]
    pub gru_drive_interval_seconds: u64,

    /// Wedge watchdog enabled
    #[serde(default = "default_true")]
    pub wedge_watchdog_enabled: bool,

    /// Wedge watchdog interval
    #[serde(default = "default_wedge_interval")]
    pub wedge_watchdog_interval_seconds: u64,

    /// Wedge threshold seconds
    #[serde(default = "default_wedge_threshold")]
    pub wedge_watchdog_threshold: u64,

    /// Wedge log tail bytes
    #[serde(default = "default_wedge_tail")]
    pub wedge_watchdog_tail_bytes: usize,

    /// Wedge cooldown seconds
    #[serde(default = "default_wedge_cooldown")]
    pub wedge_watchdog_cooldown_seconds: u64,

    /// Parked prompt watchdog enabled
    #[serde(default = "default_true")]
    pub parked_prompt_watchdog_enabled: bool,

    /// Parked prompt interval
    #[serde(default = "default_parked_interval")]
    pub parked_prompt_watchdog_interval_seconds: u64,

    /// Parked prompt min age
    #[serde(default = "default_parked_min_age")]
    pub parked_prompt_watchdog_min_age_seconds: u64,

    /// Log level
    #[serde(default = "default_log_level")]
    pub log_level: String,
}

fn default_heartbeat_interval() -> u64 { 30 }
fn default_experiment_interval() -> u64 { 30 }
fn default_role_evolution_interval() -> u64 { 900 }
fn default_gru_drive_interval() -> u64 { 300 }
fn default_wedge_interval() -> u64 { 60 }
fn default_wedge_threshold() -> u64 { 300 }
fn default_wedge_tail() -> usize { 2048 }
fn default_wedge_cooldown() -> u64 { 600 }
fn default_parked_interval() -> u64 { 120 }
fn default_parked_min_age() -> u64 { 240 }
fn default_log_level() -> String { "info".to_string() }
fn default_true() -> bool { true }

impl Default for DaemonConfig {
    fn default() -> Self {
        Self {
            heartbeat_interval_seconds: default_heartbeat_interval(),
            experiment_reconcile_interval_seconds: default_experiment_interval(),
            role_evolution_interval_seconds: default_role_evolution_interval(),
            role_evolution_auto_apply: false,
            gru_drive_enabled: false,
            gru_drive_interval_seconds: default_gru_drive_interval(),
            wedge_watchdog_enabled: default_true(),
            wedge_watchdog_interval_seconds: default_wedge_interval(),
            wedge_watchdog_threshold: default_wedge_threshold(),
            wedge_watchdog_tail_bytes: default_wedge_tail(),
            wedge_watchdog_cooldown_seconds: default_wedge_cooldown(),
            parked_prompt_watchdog_enabled: default_true(),
            parked_prompt_watchdog_interval_seconds: default_parked_interval(),
            parked_prompt_watchdog_min_age_seconds: default_parked_min_age(),
            log_level: default_log_level(),
        }
    }
}

impl DaemonConfig {
    /// Load config from gru.yaml
    pub fn load() -> anyhow::Result<Self> {
        let config_dir = minions_core::paths::minions_root().join("minions/config");
        let config_path = config_dir.join("gru.yaml");

        if !config_path.exists() {
            tracing::warn!("gru.yaml not found, using defaults");
            return Ok(Self::default());
        }

        let contents = std::fs::read_to_string(&config_path)?;
        let config: DaemonConfig = serde_yaml::from_str(&contents)?;
        Ok(config)
    }
}
