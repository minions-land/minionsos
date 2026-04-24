import { useMemo, useState, useRef } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";
import type { Task, AgentInfo } from "@shared/types";
import AgentNode from "./AgentNode";
import TaskNode from "./TaskNode";
import { useI18n } from "../i18n";

interface Props {
  tasks: Task[];
  agents: AgentInfo[];
  onSelectAgent: (id: string) => void;
  onSelectTask: (id: string) => void;
}

const nodeTypes = { agent: AgentNode, task: TaskNode };

const MAX_TASKS = 60;

function layoutGraph(nodes: Node[], edges: Edge[]): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 60, ranksep: 120 });
  for (const n of nodes) {
    const w = n.type === "agent" ? 120 : 260;
    const h = n.type === "agent" ? 100 : 100;
    g.setNode(n.id, { width: w, height: h });
  }
  for (const e of edges) g.setEdge(e.source, e.target);
  dagre.layout(g);
  const laid = nodes.map((n) => {
    const pos = g.node(n.id);
    const w = n.type === "agent" ? 120 : 260;
    const h = n.type === "agent" ? 100 : 100;
    return { ...n, position: { x: pos.x - w / 2, y: pos.y - h / 2 } };
  });
  return { nodes: laid, edges };
}

/** Build a stable fingerprint of the node/edge set so we can skip re-layout when data hasn't meaningfully changed */
function graphFingerprint(taskIds: string[], agentIds: string[], edgeCount: number): string {
  return `${taskIds.length}:${agentIds.length}:${edgeCount}:${taskIds.join(",")}`;
}

export default function NetworkGraph({ tasks, agents, onSelectAgent, onSelectTask }: Props) {
  const { t, locale } = useI18n();
  const [hideCompleted, setHideCompleted] = useState(false);
  const [hideAdj, setHideAdj] = useState(true);
  const [domainFilter, setDomainFilter] = useState("");

  // Cache previous layout to avoid re-running dagre when graph structure hasn't changed
  const layoutCache = useRef<{
    fingerprint: string;
    nodes: Node[];
    edges: Edge[];
    stats: { agents: number; tasks: number; edges: number; truncated: boolean };
  } | null>(null);

  const { nodes, edges, stats } = useMemo(() => {
    let taskList = tasks;
    if (hideAdj) taskList = taskList.filter((t) => t.type !== "adjudication");
    if (hideCompleted) taskList = taskList.filter((t) => t.status !== "completed");
    if (domainFilter) {
      const d = domainFilter.toLowerCase();
      taskList = taskList.filter((t) => t.domains.some((dom) => dom.toLowerCase().includes(d)));
    }

    // Sort by activity: active tasks first, then by recency
    const statusPriority: Record<string, number> = {
      bidding: 0,
      awaiting_retrieval: 1,
      unclaimed: 2,
      no_one_able: 3,
      completed: 4,
    };
    taskList = [...taskList].sort(
      (a, b) => (statusPriority[a.status] ?? 5) - (statusPriority[b.status] ?? 5)
    );

    // Truncate to MAX_TASKS to prevent memory explosion
    const truncated = taskList.length > MAX_TASKS;
    taskList = taskList.slice(0, MAX_TASKS);

    // Find agents that are involved in these tasks
    const involvedAgentIds = new Set<string>();
    for (const t of taskList) {
      involvedAgentIds.add(t.initiator_id);
      // Only include agents with active bids (executing/pending), not all historical bidders
      for (const b of t.bids) {
        if (b.status === "executing" || b.status === "pending") {
          involvedAgentIds.add(b.agent_id);
        }
      }
      for (const r of t.results) involvedAgentIds.add(r.agent_id);
    }

    const involvedAgents = agents.filter((a) => involvedAgentIds.has(a.agent_id));

    // Build edges (lightweight - no labels to reduce rendering cost)
    const rawEdges: Edge[] = [];
    let edgeId = 0;
    const taskIds: string[] = [];
    const agentNodeIds: string[] = [];

    for (const a of involvedAgents) {
      agentNodeIds.push(a.agent_id);
    }
    for (const t of taskList) {
      taskIds.push(t.id);

      // Initiator -> Task
      if (involvedAgentIds.has(t.initiator_id)) {
        rawEdges.push({
          id: `e${edgeId++}`,
          source: `a:${t.initiator_id}`,
          target: `t:${t.id}`,
          style: { stroke: "#0f766e", strokeWidth: 2 },
        });
      }

      // Task -> active bidders only
      for (const b of t.bids) {
        if (
          (b.status === "executing" || b.status === "pending") &&
          involvedAgentIds.has(b.agent_id) &&
          b.agent_id !== t.initiator_id
        ) {
          rawEdges.push({
            id: `e${edgeId++}`,
            source: `t:${t.id}`,
            target: `a:${b.agent_id}`,
            style: { stroke: "#174066", strokeWidth: 1.5 },
            animated: b.status === "executing",
          });
        }
      }

      // Result submitter -> Task (only if no bid edge)
      for (const r of t.results) {
        const hasBidEdge = t.bids.some(
          (b) => b.agent_id === r.agent_id && (b.status === "executing" || b.status === "pending")
        );
        if (!hasBidEdge && involvedAgentIds.has(r.agent_id)) {
          rawEdges.push({
            id: `e${edgeId++}`,
            source: `a:${r.agent_id}`,
            target: `t:${t.id}`,
            style: { stroke: "#7c3aed", strokeWidth: 1.5, strokeDasharray: "5,5" },
          });
        }
      }
    }

    const emptyResult = {
      nodes: [] as Node[],
      edges: [] as Edge[],
      stats: { agents: 0, tasks: 0, edges: 0, truncated: false },
    };
    if (taskList.length === 0 && involvedAgents.length === 0) return emptyResult;

    // Check fingerprint - skip dagre if graph structure unchanged
    const fp = graphFingerprint(taskIds, agentNodeIds, rawEdges.length);
    if (layoutCache.current && layoutCache.current.fingerprint === fp) {
      return layoutCache.current;
    }

    // Build nodes
    const rawNodes: Node[] = [];
    for (const a of involvedAgents) {
      rawNodes.push({
        id: `a:${a.agent_id}`,
        type: "agent",
        position: { x: 0, y: 0 },
        data: { agent: a },
      });
    }
    for (const t of taskList) {
      rawNodes.push({
        id: `t:${t.id}`,
        type: "task",
        position: { x: 0, y: 0 },
        data: { task: t },
      });
    }

    const result = layoutGraph(rawNodes, rawEdges);
    const output = {
      ...result,
      fingerprint: fp,
      stats: {
        agents: involvedAgents.length,
        tasks: taskList.length,
        edges: rawEdges.length,
        truncated,
      },
    };
    layoutCache.current = output;
    return output;
  }, [tasks, agents, hideCompleted, hideAdj, domainFilter]);

  return (
    <div className="h-full flex flex-col">
      {/* Toolbar */}
      <div className="shrink-0 p-3 border-b border-[rgba(23,23,23,0.08)] flex items-center gap-3 flex-wrap bg-[rgba(249,244,234,0.5)]">
        <input
          type="text"
          placeholder={t("tasks.filterDomain")}
          value={domainFilter}
          onChange={(e) => setDomainFilter(e.target.value)}
          className="eacn-input w-36 text-xs !py-1.5 !px-3"
        />
        <label className="flex items-center gap-1.5 text-xs text-[#5f5a52] cursor-pointer">
          <input
            type="checkbox"
            checked={hideCompleted}
            onChange={(e) => setHideCompleted(e.target.checked)}
            className="rounded accent-teal-600"
          />
          {t("net.hideCompleted")}
        </label>
        <label className="flex items-center gap-1.5 text-xs text-[#5f5a52] cursor-pointer">
          <input
            type="checkbox"
            checked={hideAdj}
            onChange={(e) => setHideAdj(e.target.checked)}
            className="rounded accent-teal-600"
          />
          {t("net.hideAdj")}
        </label>

        <div className="ml-auto flex items-center gap-4 text-[10px] text-[#5f5a52] font-mono">
          <span>{stats.agents} {t("topbar.agents")}</span>
          <span>{stats.tasks} {t("topbar.tasks")}</span>
          <span>{stats.edges} {t("net.connections")}</span>
          {stats.truncated && (
            <span className="text-[#df6d2d]">
              ({t("net.truncated", { n: MAX_TASKS })})
            </span>
          )}
          <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-teal-600 inline-block" /> {t("net.initiate")}</span>
          <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-[#174066] inline-block" /> {t("net.bid")}</span>
          <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-purple-600 inline-block" style={{ borderBottom: "1px dashed" }} /> {t("net.result")}</span>
        </div>
      </div>

      {/* Graph */}
      <div className="flex-1">
        {nodes.length === 0 ? (
          <div className="flex items-center justify-center h-full text-[#5f5a52] text-sm">
            {t("net.noData")}
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodeClick={(_e, node) => {
              if (node.id.startsWith("a:")) onSelectAgent(node.id.slice(2));
              else if (node.id.startsWith("t:")) onSelectTask(node.id.slice(2));
            }}
            fitView
            minZoom={0.1}
            maxZoom={2}
            proOptions={{ hideAttribution: true }}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
          >
            <Background color="rgba(23,23,23,0.08)" gap={36} />
            <Controls
              showInteractive={false}
              className="!bg-[rgba(255,251,244,0.9)] !border-[rgba(23,23,23,0.1)] !shadow-lg !rounded-xl [&>button]:!bg-[rgba(255,252,247,0.8)] [&>button]:!border-[rgba(23,23,23,0.08)] [&>button]:!text-[#5f5a52]"
            />
          </ReactFlow>
        )}
      </div>
    </div>
  );
}
