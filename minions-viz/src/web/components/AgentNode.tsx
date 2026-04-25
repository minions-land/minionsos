import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { AgentInfo } from "@shared/types";

const TIER_COLORS: Record<string, string> = {
  general: "#5f5a52",
  expert: "#174066",
  expert_general: "#1e5a8f",
  tool: "#0f766e",
};

function AgentNodeInner({ data }: NodeProps) {
  const agent = (data as { agent: AgentInfo }).agent;
  const color = TIER_COLORS[agent.tier] || "#5f5a52";

  return (
    <div className="flex flex-col items-center cursor-pointer group" style={{ width: 120 }}>
      <Handle type="target" position={Position.Top} className="!bg-transparent !border-0 !w-0 !h-0" />
      <div
        className="w-14 h-14 rounded-full flex items-center justify-center border-2 group-hover:scale-110 transition-transform"
        style={{
          borderColor: color,
          backgroundColor: `${color}18`,
          boxShadow: `0 8px 20px ${color}20`,
        }}
      >
        <span className="text-lg font-bold" style={{ color }}>
          {agent.name.charAt(0).toUpperCase()}
        </span>
      </div>
      <div className="mt-1.5 text-[10px] text-[#171717] text-center leading-tight max-w-[110px] truncate font-medium">
        {agent.name}
      </div>
      <div className="text-[8px] px-1.5 py-0.5 rounded-full mt-0.5 text-white font-mono" style={{ backgroundColor: color }}>
        {agent.tier}
      </div>
      <div className="text-[9px] text-[#df6d2d] mt-0.5 font-mono">{agent.reputation.toFixed(2)}</div>
      <Handle type="source" position={Position.Bottom} className="!bg-transparent !border-0 !w-0 !h-0" />
    </div>
  );
}

export default memo(AgentNodeInner);
