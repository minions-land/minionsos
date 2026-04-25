import { useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { Task } from "@shared/types";
import TaskNode from "./TaskNode";
import { layoutTaskTree } from "../utils/layout";
import { useI18n } from "../i18n";

interface Props {
  tasks: Task[];
  onSelect: (id: string) => void;
}

const nodeTypes = { task: TaskNode };

export default function TaskTree({ tasks, onSelect }: Props) {
  const { t } = useI18n();
  const [hideAdj, setHideAdj] = useState(true);

  const { nodes, edges } = useMemo(() => {
    let list = tasks;
    if (hideAdj) list = list.filter((t) => t.type !== "adjudication");

    const inTree = new Set<string>();
    for (const t of list) {
      if (t.parent_id || t.child_ids.length > 0) {
        inTree.add(t.id);
        if (t.parent_id) inTree.add(t.parent_id);
        for (const c of t.child_ids) inTree.add(c);
      }
    }

    const treeTasks = list.filter((t) => inTree.has(t.id));
    const taskMap = new Map(treeTasks.map((t) => [t.id, t]));

    const rawNodes: Node[] = treeTasks.map((t) => ({
      id: t.id,
      type: "task",
      position: { x: 0, y: 0 },
      data: { task: t },
    }));

    const rawEdges: Edge[] = [];
    for (const t of treeTasks) {
      for (const childId of t.child_ids) {
        if (taskMap.has(childId)) {
          rawEdges.push({
            id: `${t.id}->${childId}`,
            source: t.id,
            target: childId,
            style: { stroke: "rgba(23,23,23,0.2)" },
            animated: taskMap.get(childId)?.status === "bidding",
          });
        }
      }
    }

    if (rawNodes.length === 0) return { nodes: [], edges: [] };
    return layoutTaskTree(rawNodes, rawEdges);
  }, [tasks, hideAdj]);

  return (
    <div className="h-full flex flex-col">
      <div className="shrink-0 p-3 border-b border-[rgba(23,23,23,0.08)] flex items-center gap-3 bg-[rgba(249,244,234,0.5)]">
        <label className="flex items-center gap-1.5 text-xs text-[#5f5a52] cursor-pointer">
          <input
            type="checkbox"
            checked={hideAdj}
            onChange={(e) => setHideAdj(e.target.checked)}
            className="rounded accent-teal-600"
          />
          {t("tasks.hideAdj")}
        </label>
        <span className="text-xs text-[#5f5a52] font-mono">
          {nodes.length} {t("tree.nodes")}, {edges.length} {t("tree.edges")}
        </span>
      </div>

      <div className="flex-1">
        {nodes.length === 0 ? (
          <div className="flex items-center justify-center h-full text-[#5f5a52] text-sm">
            {t("tree.noData")}
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodeClick={(_e, node) => onSelect(node.id)}
            fitView
            minZoom={0.1}
            maxZoom={2}
            proOptions={{ hideAttribution: true }}
            nodesDraggable={false}
            nodesConnectable={false}
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
