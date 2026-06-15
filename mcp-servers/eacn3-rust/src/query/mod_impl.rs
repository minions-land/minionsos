//! 统一查询接口

use std::path::{Path, PathBuf};
use crate::{Result, Error};
use crate::eacn3::{Message, MessageStore, Task, TaskStatus, TaskStore};
use crate::memory::{DraftDag, DraftGraph, ReelIndex};
use crate::memory::draft::HubNode;

/// 任务查询过滤器
pub enum TaskFilter {
    ByStatus(TaskStatus),
    ByInitiator(String),
}

/// 统一的 Memory + EACN3 查询接口
///
/// 注意：rusqlite::Connection 不是 Sync，所以不要求 Send + Sync
pub trait UnifiedQuery {
    // ===== 消息层 =====
    fn query_messages(&self, agent_id: &str, limit: usize) -> Result<Vec<Message>>;
    fn mark_messages_read(&self, msg_ids: &[String]) -> Result<usize>;

    // ===== 任务层 =====
    fn query_tasks(&self, filter: TaskFilter) -> Result<Vec<Task>>;

    // ===== 历史进展（Graph Memory）=====
    fn draft_shortest_path(&self, from: &str, to: &str) -> Result<Vec<String>>;
    fn draft_hub_nodes(&self, top_n: usize) -> Result<Vec<HubNode>>;
    fn draft_node_count(&self) -> Result<usize>;
    fn draft_edge_count(&self) -> Result<usize>;

    // ===== Reel (L0) =====
    fn read_reel(&self, ref_str: &str) -> Result<Vec<serde_json::Value>>;
}

/// 项目存储（实现统一查询接口）
pub struct ProjectStore {
    project_id: String,
    project_path: PathBuf,
    message_store: MessageStore,
    task_store: TaskStore,
    draft_graph: Option<DraftGraph>,
    reel_index: Option<ReelIndex>,
}

impl ProjectStore {
    /// 打开项目存储
    pub fn open(project_path: &Path) -> Result<Self> {
        if !project_path.exists() {
            return Err(Error::InvalidProjectPath);
        }

        let project_id = project_path
            .file_name()
            .and_then(|s| s.to_str())
            .ok_or(Error::InvalidProjectPath)?
            .to_string();

        // 打开 EACN3 数据库
        let db_path = project_path.join("eacn3.db");
        let message_store = MessageStore::new(&db_path)?;
        let task_store = TaskStore::new(&db_path)?;

        // 加载 Draft DAG（如果存在）
        let draft_path = project_path.join("graph/draft.json");
        let draft_graph = if draft_path.exists() {
            let draft_json = std::fs::read_to_string(&draft_path)?;
            let dag: DraftDag = serde_json::from_str(&draft_json)?;
            Some(DraftGraph::from_dag(&dag)?)
        } else {
            None
        };

        // 加载 Reel 索引（如果存在）
        let reel_path = project_path.join("graph/reel/reel-index.jsonl");
        let reel_index = if reel_path.exists() {
            Some(ReelIndex::load(&reel_path)?)
        } else {
            None
        };

        Ok(Self {
            project_id,
            project_path: project_path.to_path_buf(),
            message_store,
            task_store,
            draft_graph,
            reel_index,
        })
    }

    pub fn project_id(&self) -> &str {
        &self.project_id
    }

    pub fn project_path(&self) -> &Path {
        &self.project_path
    }
}

impl UnifiedQuery for ProjectStore {
    fn query_messages(&self, agent_id: &str, limit: usize) -> Result<Vec<Message>> {
        self.message_store.query_unread(agent_id, limit)
    }

    fn mark_messages_read(&self, msg_ids: &[String]) -> Result<usize> {
        self.message_store.mark_read(msg_ids)
    }

    fn query_tasks(&self, filter: TaskFilter) -> Result<Vec<Task>> {
        match filter {
            TaskFilter::ByStatus(status) => {
                self.task_store.query_by_status(&status)
            }
            TaskFilter::ByInitiator(initiator_id) => {
                self.task_store.query_by_initiator(&initiator_id)
            }
        }
    }

    fn draft_shortest_path(&self, from: &str, to: &str) -> Result<Vec<String>> {
        self.draft_graph
            .as_ref()
            .ok_or(Error::InvalidProjectPath)?
            .shortest_path(from, to)
    }

    fn draft_hub_nodes(&self, top_n: usize) -> Result<Vec<HubNode>> {
        Ok(self
            .draft_graph
            .as_ref()
            .ok_or(Error::InvalidProjectPath)?
            .hub_nodes(top_n))
    }

    fn draft_node_count(&self) -> Result<usize> {
        Ok(self
            .draft_graph
            .as_ref()
            .ok_or(Error::InvalidProjectPath)?
            .node_count())
    }

    fn draft_edge_count(&self) -> Result<usize> {
        Ok(self
            .draft_graph
            .as_ref()
            .ok_or(Error::InvalidProjectPath)?
            .edge_count())
    }

    fn read_reel(&self, ref_str: &str) -> Result<Vec<serde_json::Value>> {
        self.reel_index
            .as_ref()
            .ok_or(Error::InvalidProjectPath)?
            .read_history(ref_str)
    }
}
