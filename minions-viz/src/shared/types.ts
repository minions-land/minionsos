// ============================================
// Shared types for MinionsOS Project Observatory
// ============================================

export type TaskStatus = "unclaimed" | "bidding" | "awaiting_retrieval" | "completed" | "no_one_able";
export type TaskType = "normal" | "adjudication";
export type TaskLevel = "general" | "expert" | "expert_general" | "tool";
export type BidStatus = "pending" | "accepted" | "rejected" | "waiting" | "executing";

export interface Bid {
  agent_id: string;
  server_id: string;
  confidence: number;
  price: number;
  status: BidStatus;
}

export interface Adjudication {
  adjudicator_id: string;
  verdict: string;
  score: number;
}

export interface Result {
  agent_id: string;
  content: unknown;
  selected: boolean;
  adjudications: Adjudication[];
}

export interface HumanContact {
  allowed: boolean;
  contact_id?: string;
  timeout_s?: number;
}

export interface Task {
  id: string;
  status: TaskStatus;
  type: TaskType;
  initiator_id: string;
  server_id: string;
  domains: string[];
  content: Record<string, unknown>;
  budget: number;
  remaining_budget: number | null;
  deadline: string | null;
  parent_id: string | null;
  child_ids: string[];
  depth: number;
  max_depth: number;
  max_concurrent_bidders: number;
  bids: Bid[];
  results: Result[];
  budget_locked: boolean;
  level: TaskLevel;
  invited_agent_ids: string[];
  human_contact: HumanContact | null;
}

export interface Skill {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
}

export interface AgentCard {
  agent_id: string;
  name: string;
  domains: string[];
  skills: Skill[];
  url: string;
  server_id: string;
  network_id: string;
  description: string;
  tier: string;
}

export interface AgentInfo extends AgentCard {
  reputation: number;
  balance: { available: number; frozen: number };
}

export interface ClusterMember {
  node_id: string;
  endpoint: string;
  domains: string[];
  status: string;
  last_seen: string;
  connected_agents: number;
}

export interface ClusterStatus {
  mode: string;
  local: {
    node_id: string;
    endpoint: string;
    domains: string[];
    status: string;
    version: string;
    joined_at: string;
  };
  members: ClusterMember[];
  member_count: number;
  online_count: number;
  seed_nodes: string[];
}

export interface LogEntry {
  fn_name: string;
  args: Record<string, unknown>;
  result: unknown;
  timestamp: string;
  error: string | null;
  task_id: string | null;
  agent_id: string | null;
  server_id: string | null;
}

export interface Message {
  id: string;
  from_agent_id: string;
  to_agent_id: string;
  task_id: string | null;
  content: unknown;
  timestamp: string;
}

// ── MinionsOS types ─────────────────────────────────────────────────

export interface MosRoleEntry {
  name: string;
  state: "active" | "sleeping" | "dismissed";
  pid: number | null;
  spawned_at: string | null;
  poll_interval: string | null;
  eacn_agent_id?: string | null;
  last_seen?: string | null;
  current_task?: string | null;
  blocked_reason?: string | null;
}

export interface MosProject {
  port: number;
  real_name: string;
  status: "active" | "dormant" | "closed";
  created: string;
  dormant_at: string | null;
  closed_at: string | null;
  venue: string | null;
  upstream_branch: string;
  current_branch: string;
  active_roles: MosRoleEntry[];
}

export interface GruInfo {
  id: string;
  label: string;
  rootPath: string;
  parentRepo: string;
  stateDir: string;
  lastSeen: string | null;
  online: boolean;
  projects: MosProject[];
}

export interface MosOverview {
  port: number;
  project: MosProject | null;
  claude_md: string | null;
  meta: Record<string, unknown> | null;
  project_dir: string;
  workspace_dir: string;
  artifacts_dir: string;
}

export type MosThresholdStatus = "ok" | "soft" | "hard" | "veto";

export interface MosScratchpad {
  role: string;
  path: string;
  exists: boolean;
  bytes: number;
  approx_tokens: number;
  threshold_status: MosThresholdStatus;
  mtime: number | null;
}

export interface MosArtifactNode {
  name: string;
  path: string;
  kind: "dir" | "file";
  size: number;
  mtime: number;
  children?: MosArtifactNode[];
}

export interface NetworkSnapshot {
  tasks: Task[];
  agents: AgentInfo[];
  cluster: ClusterStatus | null;
  logs: LogEntry[];
  messages: Message[];
  connected: boolean;
  eacnEndpoint: string;
  lastUpdate: number;
  /** Port of selected project, relative to selectedGruId. */
  selectedPort: number | null;
  selectedGruId: string | null;
  grus: GruInfo[];
}

// ── Scratchpad types ──────────────────────────────────────────────

export interface ScratchpadNode {
  id: string;
  type: string;
  text: string;
  support_status: string;
  author_role: string;
  created_at: string;
  evidence_tag: string;
  metadata: Record<string, unknown>;
}

export interface ScratchpadEdge {
  from_id: string;
  to_id: string;
  relation: string;
  strength: number;
  created_at: string;
  author_role: string;
}

export interface ScratchpadData {
  project_port: number;
  root_question: string;
  nodes: ScratchpadNode[];
  edges: ScratchpadEdge[];
}

export type WsMessage =
  | { type: "snapshot"; data: NetworkSnapshot }
  | { type: "tasks:update"; data: Task[] }
  | { type: "agents:update"; data: AgentInfo[] }
  | { type: "cluster:update"; data: ClusterStatus | null }
  | { type: "logs:update"; data: LogEntry[] }
  | { type: "messages:update"; data: Message[] }
  | { type: "connection:status"; data: { connected: boolean } }
  | { type: "grus:update"; data: GruInfo[] }
  | { type: "selected"; data: { gruId: string | null; port: number | null } }
  | {
      type: "role-log:append";
      data: { gruId: string; port: number; role: string; chunk: string };
    }
  // legacy
  | { type: "projects:update"; data: MosProject[] }
  | { type: "selected_project"; data: { port: number | null } }
  | { type: "select_project"; port: number | null }
  | { type: "select"; gruId: string | null; port: number | null };
