mod config;
mod health;

use anyhow::Result;
use config::DaemonConfig;
use health::{tick_health_monitor, CrashCounter};
use minions_core::StateStore;
use reqwest::Client;
use std::time::Duration;
use tokio::time;
use tracing::{info, error};

#[tokio::main]
async fn main() -> Result<()> {
    // Load config
    let config = DaemonConfig::load()?;

    // Initialize logging
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new(&config.log_level))
        )
        .init();

    info!("MinionsOS Daemon (minionsd) starting...");
    info!("Config loaded: heartbeat_interval={}s", config.heartbeat_interval_seconds);

    // Initialize components
    let store = StateStore::new();
    let client = Client::builder()
        .timeout(Duration::from_secs(10))
        .build()?;
    let mut crash_counter = CrashCounter::new();

    // Verify state exists
    if !store.exists() {
        error!("projects.json not found. Make sure MinionsOS is initialized.");
        std::process::exit(1);
    }

    info!("State store initialized");

    // Main monitoring loop
    let mut health_interval = time::interval(Duration::from_secs(config.heartbeat_interval_seconds));
    health_interval.set_missed_tick_behavior(time::MissedTickBehavior::Skip);

    info!("Health monitor started (interval={}s)", config.heartbeat_interval_seconds);

    loop {
        health_interval.tick().await;

        match tick_health_monitor(&client, &store, &mut crash_counter).await {
            Ok(events) => {
                if !events.is_empty() {
                    for event in events {
                        info!("Health event: {}", event);
                    }
                }
            }
            Err(e) => {
                error!("Health monitor tick error: {}", e);
            }
        }
    }
}
