//! EACN3 + Memory unified MCP server
//!
//! 统一的查询接口，包含：
//! 1. 消息层（EACN3 messages）
//! 2. 任务层（EACN3 tasks）
//! 3. 历史进展（Graph Memory: L0 Reel + L1 Draft）

pub mod eacn3;
pub mod memory;
pub mod query;
pub mod error;

pub use error::{Error, Result};
pub use query::{ProjectStore, UnifiedQuery};
