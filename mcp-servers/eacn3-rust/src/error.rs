//! Error types

use thiserror::Error;

#[derive(Error, Debug)]
pub enum Error {
    #[error("Database error: {0}")]
    Database(#[from] rusqlite::Error),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),

    #[error("Node not found: {0}")]
    NodeNotFound(String),

    #[error("Path not found between nodes")]
    PathNotFound,

    #[error("Reel reference not found: {0}")]
    ReelRefNotFound(String),

    #[error("Invalid project path")]
    InvalidProjectPath,

    #[error("Team setup not implemented")]
    TeamSetupNotImplemented,
}

pub type Result<T> = std::result::Result<T, Error>;
