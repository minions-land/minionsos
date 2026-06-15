//! EACN3 任务层

use chrono::{DateTime, Utc};
use rusqlite::{Connection, params};
use serde::{Deserialize, Serialize};
use std::path::Path;
use crate::Result;

/// 任务状态
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum TaskStatus {
    Unclaimed,
    Bidding,
    AwaitingRetrieval,
    Completed,
    NoOneAble,
}

/// 任务内容
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskContent {
    pub description: String,
    pub expected_output: serde_json::Value,
    pub discussions: Vec<String>,
}

/// 竞价
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Bid {
    pub agent_id: String,
    pub confidence: f32,
    pub price: f64,
    pub status: String,
}

/// 任务结果
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskResult {
    pub agent_id: String,
    pub content: serde_json::Value,
    pub selected: bool,
    pub adjudications: Vec<serde_json::Value>,
}

/// 任务
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Task {
    pub id: String,
    pub created_at: DateTime<Utc>,
    pub content: TaskContent,
    #[serde(rename = "type")]
    pub task_type: String,
    pub initiator_id: String,
    pub domains: Vec<String>,
    pub status: TaskStatus,
    pub bids: Vec<Bid>,
    pub results: Vec<TaskResult>,
    pub budget: f64,
    pub deadline: Option<DateTime<Utc>>,
    pub level: String,
}

/// 任务存储（SQLite）
pub struct TaskStore {
    conn: Connection,
}

impl TaskStore {
    pub fn new(db_path: &Path) -> Result<Self> {
        let conn = Connection::open(db_path)?;

        // 创建表
        conn.execute(
            "CREATE TABLE IF NOT EXISTS tasks (
                task_id     TEXT PRIMARY KEY,
                data        TEXT NOT NULL,
                status      TEXT NOT NULL,
                initiator_id TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                deadline    TEXT,
                parent_id   TEXT DEFAULT NULL
            )",
            [],
        )?;

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)",
            [],
        )?;

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_initiator ON tasks(initiator_id)",
            [],
        )?;

        Ok(Self { conn })
    }

    /// 按状态查询任务
    pub fn query_by_status(&self, status: &TaskStatus) -> Result<Vec<Task>> {
        let status_str = match status {
            TaskStatus::Unclaimed => "UNCLAIMED",
            TaskStatus::Bidding => "BIDDING",
            TaskStatus::AwaitingRetrieval => "AWAITING_RETRIEVAL",
            TaskStatus::Completed => "COMPLETED",
            TaskStatus::NoOneAble => "NO_ONE_ABLE",
        };

        let mut stmt = self.conn.prepare(
            "SELECT data FROM tasks WHERE status = ?1 ORDER BY created_at DESC"
        )?;

        let tasks = stmt.query_map(params![status_str], |row| {
            let json: String = row.get(0)?;
            Ok(serde_json::from_str(&json).unwrap())
        })?;

        tasks.collect::<rusqlite::Result<Vec<_>>>()
            .map_err(Into::into)
    }

    /// 按发起者查询任务
    pub fn query_by_initiator(&self, initiator_id: &str) -> Result<Vec<Task>> {
        let mut stmt = self.conn.prepare(
            "SELECT data FROM tasks WHERE initiator_id = ?1 ORDER BY created_at DESC"
        )?;

        let tasks = stmt.query_map(params![initiator_id], |row| {
            let json: String = row.get(0)?;
            Ok(serde_json::from_str(&json).unwrap())
        })?;

        tasks.collect::<rusqlite::Result<Vec<_>>>()
            .map_err(Into::into)
    }

    /// 插入新任务（测试用）
    pub fn insert(&self, task: &Task) -> Result<()> {
        let status_str = match &task.status {
            TaskStatus::Unclaimed => "UNCLAIMED",
            TaskStatus::Bidding => "BIDDING",
            TaskStatus::AwaitingRetrieval => "AWAITING_RETRIEVAL",
            TaskStatus::Completed => "COMPLETED",
            TaskStatus::NoOneAble => "NO_ONE_ABLE",
        };

        self.conn.execute(
            "INSERT INTO tasks (task_id, data, status, initiator_id, created_at, deadline, parent_id)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, NULL)",
            params![
                &task.id,
                serde_json::to_string(task).unwrap(),
                status_str,
                &task.initiator_id,
                task.created_at.to_rfc3339(),
                task.deadline.map(|dt| dt.to_rfc3339()),
            ],
        )?;

        Ok(())
    }
}
