import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { Task } from "@shared/types";
import { statusColor, statusLabel, shortId, truncate } from "../utils/format";

const STATUS_BG: Record<string, string> = {
  unclaimed: "rgba(120,113,108,0.08)",
  bidding: "rgba(15,118,110,0.08)",
  awaiting_retrieval: "rgba(223,109,45,0.08)",
  completed: "rgba(5,150,105,0.08)",
  no_one_able: "rgba(239,68,68,0.08)",
};

function TaskNodeInner({ data }: NodeProps) {
  const task = (data as { task: Task }).task;
  const desc =
    typeof task.content.description === "string"
      ? task.content.description
      : JSON.stringify(task.content).slice(0, 60);

  return (
    <div
      className="border rounded-2xl p-3 w-[240px] cursor-pointer hover:shadow-lg transition-shadow"
      style={{
        background: STATUS_BG[task.status] || "rgba(255,252,247,0.8)",
        borderColor: "rgba(23,23,23,0.1)",
        boxShadow: "0 12px 28px rgba(28,19,5,0.06)",
      }}
    >
      <Handle type="target" position={Position.Top} className="!bg-[#5f5a52] !w-2 !h-2" />

      <div className="flex items-center gap-1.5 mb-1">
        <span className={`w-2 h-2 rounded-full shrink-0 ${statusColor(task.status)}`} />
        <span className="text-[10px] text-[#5f5a52] font-medium">{statusLabel(task.status)}</span>
        {task.type === "adjudication" && (
          <span className="text-[9px] px-1 bg-[#df6d2d] text-white rounded-full ml-auto">Adj</span>
        )}
      </div>

      <div className="text-[10px] text-[#5f5a52] font-mono mb-1">{shortId(task.id)}</div>
      <div className="text-xs text-[#171717] line-clamp-2 mb-1">{truncate(desc, 80)}</div>

      <div className="flex gap-2 text-[9px] text-[#5f5a52] font-mono">
        {task.budget > 0 && <span>{task.budget} budget</span>}
        <span>{task.bids.length} bids</span>
        <span>{task.results.length} results</span>
        <span>L{task.depth}</span>
      </div>

      <Handle type="source" position={Position.Bottom} className="!bg-[#5f5a52] !w-2 !h-2" />
    </div>
  );
}

export default memo(TaskNodeInner);
