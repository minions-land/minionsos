//! Reel Index (L0 Memory - 指向 Claude Code History JSON 的指针)

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::fs::File;
use std::io::{BufRead, BufReader};
use std::path::Path;
use crate::Result;

/// Reel 索引条目（指向 Claude Code History JSON）
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReelEntry {
    /// 引用字符串："<role>/<session_id>/<tool_use_id>"
    #[serde(rename = "ref")]
    pub ref_str: String,

    /// 时间戳
    pub ts: DateTime<Utc>,

    /// 类型（subagent 或 direct）
    pub kind: String,

    /// 工具名称（Agent 或 Task）
    pub tool_name: String,

    /// Claude Code JSONL 文件的绝对路径
    pub claude_jsonl: String,

    /// 关联的 Draft 节点 ID 列表
    pub draft_node_refs: Vec<String>,
}

/// Reel 索引（JSONL 文件的内存表示）
pub struct ReelIndex {
    entries: Vec<ReelEntry>,
}

impl ReelIndex {
    /// 从 JSONL 文件加载
    pub fn load(path: &Path) -> Result<Self> {
        if !path.exists() {
            // 如果文件不存在，返回空索引
            return Ok(Self { entries: vec![] });
        }

        let file = File::open(path)?;
        let reader = BufReader::new(file);
        let mut entries = Vec::new();

        for line in reader.lines() {
            let line = line?;
            if line.trim().is_empty() {
                continue;
            }
            match serde_json::from_str::<ReelEntry>(&line) {
                Ok(entry) => entries.push(entry),
                Err(e) => {
                    eprintln!("Warning: Failed to parse reel entry: {}", e);
                    continue;
                }
            }
        }

        Ok(Self { entries })
    }

    /// 根据引用字符串查找条目
    pub fn get(&self, ref_str: &str) -> Option<&ReelEntry> {
        self.entries.iter().find(|e| e.ref_str == ref_str)
    }

    /// 读取 Claude Code History JSON 的指定范围
    pub fn read_history(&self, ref_str: &str) -> Result<Vec<serde_json::Value>> {
        let entry = self.get(ref_str)
            .ok_or_else(|| crate::Error::ReelRefNotFound(ref_str.to_string()))?;

        // 读取外部 JSONL 文件
        let file = File::open(&entry.claude_jsonl)?;
        let reader = BufReader::new(file);
        let mut lines = Vec::new();

        for line in reader.lines() {
            let line = line?;
            if line.trim().is_empty() {
                continue;
            }
            match serde_json::from_str(&line) {
                Ok(value) => lines.push(value),
                Err(e) => {
                    eprintln!("Warning: Failed to parse history line: {}", e);
                    continue;
                }
            }
        }

        Ok(lines)
    }

    /// 所有条目
    pub fn entries(&self) -> &[ReelEntry] {
        &self.entries
    }
}
