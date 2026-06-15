//! EACN3 core functionality

pub mod message;
pub mod task;

pub use message::{Message, MessageStatus, MessageStore};
pub use task::{Task, TaskStatus, TaskContent, Bid, TaskResult, TaskStore};
