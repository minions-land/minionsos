//! EACN3 消息层

use chrono::{DateTime, Utc};
use rusqlite::{Connection, params};
use serde::{Deserialize, Serialize};
use std::path::Path;
use crate::Result;

/// 消息状态
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MessageStatus {
    Unread,
    Read,
    Expired,
}

/// EACN3 消息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message {
    pub msg_id: String,
    pub agent_id: String,
    #[serde(rename = "type")]
    pub msg_type: String,
    pub task_id: String,
    pub payload: serde_json::Value,
    pub created_at: DateTime<Utc>,
    pub expires_at: Option<DateTime<Utc>>,
    pub status: MessageStatus,
}

/// 消息存储（SQLite）
pub struct MessageStore {
    conn: Connection,
}

impl MessageStore {
    pub fn new(db_path: &Path) -> Result<Self> {
        let conn = Connection::open(db_path)?;

        // 创建表
        conn.execute(
            "CREATE TABLE IF NOT EXISTS messages (
                msg_id      TEXT PRIMARY KEY,
                agent_id    TEXT NOT NULL,
                type        TEXT NOT NULL,
                task_id     TEXT DEFAULT '',
                payload     TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                expires_at  TEXT,
                status      TEXT DEFAULT 'unread'
            )",
            [],
        )?;

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_agent ON messages(agent_id, status)",
            [],
        )?;

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at)",
            [],
        )?;

        Ok(Self { conn })
    }

    /// 查询未读消息
    pub fn query_unread(&self, agent_id: &str, limit: usize) -> Result<Vec<Message>> {
        let mut stmt = self.conn.prepare(
            "SELECT msg_id, agent_id, type, task_id, payload, created_at, expires_at, status
             FROM messages
             WHERE agent_id = ?1 AND status = 'unread'
             ORDER BY created_at
             LIMIT ?2"
        )?;

        let messages = stmt.query_map(params![agent_id, limit], |row| {
            let payload_str: String = row.get(4)?;
            let created_at_str: String = row.get(5)?;
            let expires_at_str: Option<String> = row.get(6)?;

            Ok(Message {
                msg_id: row.get(0)?,
                agent_id: row.get(1)?,
                msg_type: row.get(2)?,
                task_id: row.get(3)?,
                payload: serde_json::from_str(&payload_str).unwrap(),
                created_at: DateTime::parse_from_rfc3339(&created_at_str)
                    .unwrap()
                    .with_timezone(&Utc),
                expires_at: expires_at_str.map(|s| {
                    DateTime::parse_from_rfc3339(&s)
                        .unwrap()
                        .with_timezone(&Utc)
                }),
                status: MessageStatus::Unread,
            })
        })?;

        messages.collect::<rusqlite::Result<Vec<_>>>()
            .map_err(Into::into)
    }

    /// 标记为已读
    pub fn mark_read(&self, msg_ids: &[String]) -> Result<usize> {
        if msg_ids.is_empty() {
            return Ok(0);
        }

        let placeholders = msg_ids.iter().map(|_| "?").collect::<Vec<_>>().join(",");
        let query = format!("UPDATE messages SET status = 'read' WHERE msg_id IN ({})", placeholders);

        let mut stmt = self.conn.prepare(&query)?;
        let params: Vec<&dyn rusqlite::ToSql> = msg_ids.iter()
            .map(|id| id as &dyn rusqlite::ToSql)
            .collect();

        Ok(stmt.execute(&params[..])?)
    }

    /// 插入新消息（测试用）
    pub fn insert(&self, msg: &Message) -> Result<()> {
        let status_str = match msg.status {
            MessageStatus::Unread => "unread",
            MessageStatus::Read => "read",
            MessageStatus::Expired => "expired",
        };

        self.conn.execute(
            "INSERT INTO messages (msg_id, agent_id, type, task_id, payload, created_at, expires_at, status)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
            params![
                &msg.msg_id,
                &msg.agent_id,
                &msg.msg_type,
                &msg.task_id,
                serde_json::to_string(&msg.payload).unwrap(),
                msg.created_at.to_rfc3339(),
                msg.expires_at.map(|dt| dt.to_rfc3339()),
                status_str,
            ],
        )?;

        Ok(())
    }
}
