//! Draft DAG (L1 Memory)

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use petgraph::graph::{DiGraph, NodeIndex};
use petgraph::algo::dijkstra;
use petgraph::visit::EdgeRef;
use crate::Result;

/// Draft 节点类型（11 种标准类型）
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DraftNodeType {
    Hypothesis,
    Question,
    Assumption,
    Experiment,
    Result,
    Citation,
    Decision,
    #[serde(rename = "dead_end")]
    DeadEnd,
    Insight,
    Method,
    Bootstrap,
}

/// Draft 节点支持状态
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DraftSupportStatus {
    Unverified,
    Tentative,
    Verified,
    Refuted,
    Blocked,
    #[serde(rename = "out_of_scope")]
    OutOfScope,
}

/// Draft 节点来源
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DraftProvenance {
    Extracted,
    Inferred,
    Speculative,
}

/// Draft 节点元数据
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct DraftNodeMetadata {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reel_ref: Option<String>,
    #[serde(default)]
    pub pending_plan: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub motif_kind: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub topic: Option<String>,
}

/// Draft 节点
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DraftNode {
    pub id: String,
    #[serde(rename = "type")]
    pub node_type: DraftNodeType,
    pub text: String,
    pub support_status: DraftSupportStatus,
    pub author_role: String,
    pub created_at: DateTime<Utc>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub evidence_tag: Option<String>,
    pub provenance: DraftProvenance,
    pub confidence: f32,
    #[serde(default)]
    pub metadata: DraftNodeMetadata,
}

/// Draft 边关系类型
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DraftEdgeRelation {
    Supports, Verifies,
    #[serde(rename = "verified_by")]
    VerifiedBy,
    Reaffirms, Ratifies, Corroborates,
    #[serde(rename = "concurs_with")]
    ConcursWith,
    Endorses, Strengthens,
    #[serde(rename = "partially_corroborates")]
    PartiallyCorroborates,
    Reviews, Resolves, Completes, Delivers,
    Refines, Tests, Implements,
    #[serde(rename = "depends_on")]
    DependsOn,
    Contradicts, Supersedes, Absorbs, Blocks,
    #[serde(rename = "deferred_from")]
    DeferredFrom,
    Cites,
    #[serde(rename = "derived_from")]
    DerivedFrom,
    #[serde(rename = "relates_to")]
    RelatesTo,
}

impl DraftEdgeRelation {
    pub fn weight(&self) -> f32 {
        match self {
            Self::Supports | Self::Verifies | Self::VerifiedBy
            | Self::Reaffirms | Self::Ratifies | Self::Corroborates => 1.0,
            Self::ConcursWith | Self::Endorses | Self::Strengthens => 0.8,
            Self::PartiallyCorroborates | Self::Reviews => 0.5,
            Self::Resolves | Self::Completes | Self::Delivers => 0.6,
            Self::Refines => 0.3,
            Self::Tests | Self::Implements => 0.2,
            Self::DependsOn => 0.1,
            Self::Contradicts | Self::Supersedes => -1.0,
            Self::Absorbs => -0.8,
            Self::Blocks | Self::DeferredFrom => -0.4,
            Self::Cites | Self::DerivedFrom | Self::RelatesTo => 0.1,
        }
    }
}

/// Draft 边
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DraftEdge {
    pub from_id: String,
    pub to_id: String,
    pub relation: DraftEdgeRelation,
    pub strength: f32,
    pub created_at: DateTime<Utc>,
    pub author_role: String,
}

/// Draft DAG
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DraftDag {
    pub project_port: u16,
    pub root_question: String,
    pub nodes: Vec<DraftNode>,
    pub edges: Vec<DraftEdge>,
}

/// Draft 图计算引擎
pub struct DraftGraph {
    graph: DiGraph<DraftNode, DraftEdge>,
    id_map: HashMap<String, NodeIndex>,
}

impl DraftGraph {
    pub fn from_dag(dag: &DraftDag) -> Result<Self> {
        let mut graph = DiGraph::new();
        let mut id_map = HashMap::new();
        for node in &dag.nodes {
            let idx = graph.add_node(node.clone());
            id_map.insert(node.id.clone(), idx);
        }
        for edge in &dag.edges {
            if let (Some(&from_idx), Some(&to_idx)) =
                (id_map.get(&edge.from_id), id_map.get(&edge.to_id))
            {
                graph.add_edge(from_idx, to_idx, edge.clone());
            }
        }
        Ok(Self { graph, id_map })
    }

    pub fn get_node(&self, node_id: &str) -> Option<&DraftNode> {
        self.id_map.get(node_id).map(|&idx| &self.graph[idx])
    }

    pub fn shortest_path(&self, from: &str, to: &str) -> Result<Vec<String>> {
        let from_idx = self.id_map.get(from)
            .ok_or_else(|| crate::Error::NodeNotFound(from.to_string()))?;
        let to_idx = self.id_map.get(to)
            .ok_or_else(|| crate::Error::NodeNotFound(to.to_string()))?;
        let distances = dijkstra(&self.graph, *from_idx, Some(*to_idx),
            |edge_ref| {
                let edge = edge_ref.weight();
                if edge.strength > 0.0 { 1.0 / edge.strength } else { f32::MAX }
            });
        if !distances.contains_key(to_idx) {
            return Err(crate::Error::PathNotFound);
        }
        let mut path = vec![to.to_string()];
        let mut current = *to_idx;
        while current != *from_idx {
            let mut found = false;
            for edge in self.graph.edges_directed(current, petgraph::Direction::Incoming) {
                let source = edge.source();
                if distances.contains_key(&source) {
                    path.push(self.graph[source].id.clone());
                    current = source;
                    found = true;
                    break;
                }
            }
            if !found { break; }
        }
        path.reverse();
        Ok(path)
    }

    pub fn hub_nodes(&self, top_n: usize) -> Vec<HubNode> {
        let mut hubs: Vec<_> = self.graph.node_indices()
            .map(|idx| {
                let node = &self.graph[idx];
                let degree = self.graph.neighbors(idx).count();
                HubNode {
                    id: node.id.clone(),
                    text: node.text.clone(),
                    degree,
                    score: degree as f32,
                }
            }).collect();
        hubs.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap());
        hubs.into_iter().take(top_n).collect()
    }

    pub fn node_count(&self) -> usize { self.graph.node_count() }
    pub fn edge_count(&self) -> usize { self.graph.edge_count() }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HubNode {
    pub id: String,
    pub text: String,
    pub degree: usize,
    pub score: f32,
}
