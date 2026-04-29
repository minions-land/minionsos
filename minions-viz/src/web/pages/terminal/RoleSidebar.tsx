import { useMemo } from "react";
import { getRoleIdentity, ROLES } from "../../utils/roleIdentity";
import {
  Crown,
  Eye,
  CodeBlock,
  Flask,
  PenNib,
  MagnifyingGlass,
  Scales,
  Robot,
} from "@phosphor-icons/react";
import type { IconProps } from "@phosphor-icons/react";
import type { AgentInfo } from "@shared/types";
import type { ComponentType } from "react";

const ICON_MAP: Record<string, ComponentType<IconProps>> = {
  Crown,
  Eye,
  CodeBlock,
  Flask,
  PenNib,
  MagnifyingGlass,
  Scales,
  Robot,
};

type RoleState = "active" | "sleeping" | "dismissed";

interface RoleEntry {
  key: string;
  label: string;
  color: string;
  colorRgb: string;
  iconName: string;
  state: RoleState;
  bufferCount: number;
}

interface Props {
  agents: AgentInfo[];
  selectedRole: string | null;
  onSelect: (role: string) => void;
}

const STATE_ORDER: Record<RoleState, number> = { active: 0, sleeping: 1, dismissed: 2 };

export default function RoleSidebar({ agents, selectedRole, onSelect }: Props) {
  const agentSet = useMemo(() => {
    const m = new Map<string, AgentInfo>();
    for (const a of agents) {
      const id = getRoleIdentity(a.agent_id);
      m.set(id.key, a);
    }
    return m;
  }, [agents]);

  const entries = useMemo<RoleEntry[]>(() => {
    const list: RoleEntry[] = Object.values(ROLES).map((r) => {
      const agent = agentSet.get(r.key);
      return {
        key: r.key,
        label: r.label,
        color: r.color,
        colorRgb: r.colorRgb,
        iconName: r.icon,
        state: agent ? "active" : "sleeping",
        bufferCount: 0,
      };
    });
    list.sort((a, b) => STATE_ORDER[a.state] - STATE_ORDER[b.state]);
    return list;
  }, [agentSet]);

  return (
    <div
      style={{
        width: 180,
        minWidth: 180,
        height: "100%",
        background: "var(--panel-bg)",
        borderRight: "1px solid var(--line)",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          padding: "10px 12px 6px",
          fontSize: 10,
          fontFamily: "var(--font-mono)",
          color: "var(--muted)",
          textTransform: "uppercase",
          letterSpacing: "0.08em",
        }}
      >
        Roles
      </div>
      <div style={{ flex: 1, overflowY: "auto" }}>
        {entries.map((entry) => {
          const selected = selectedRole === entry.key;
          const Icon = ICON_MAP[entry.iconName] ?? Robot;
          return (
            <button
              key={entry.key}
              onClick={() => onSelect(entry.key)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                width: "100%",
                padding: "8px 12px",
                border: "none",
                borderLeft: selected
                  ? `3px solid ${entry.color}`
                  : "3px solid transparent",
                background: selected
                  ? `rgba(${entry.colorRgb}, 0.1)`
                  : "transparent",
                cursor: "pointer",
                transition: "all 200ms ease",
                textAlign: "left",
              }}
              onMouseEnter={(e) => {
                if (!selected) {
                  e.currentTarget.style.background = `rgba(${entry.colorRgb}, 0.05)`;
                }
              }}
              onMouseLeave={(e) => {
                if (!selected) {
                  e.currentTarget.style.background = "transparent";
                }
              }}
            >
              <Icon size={24} weight="duotone" color={entry.color} />
              <span
                style={{
                  flex: 1,
                  fontSize: 11,
                  fontFamily: "var(--font-mono)",
                  color: selected ? "var(--text)" : "var(--text-2)",
                }}
              >
                {entry.label}
              </span>
              <StateDot state={entry.state} />
            </button>
          );
        })}
      </div>
    </div>
  );
}

function StateDot({ state }: { state: RoleState }) {
  const color =
    state === "active"
      ? "#22c55e"
      : state === "sleeping"
        ? "#f59e0b"
        : "#6b7280";

  return (
    <span
      style={{
        width: 8,
        height: 8,
        borderRadius: "50%",
        background: color,
        flexShrink: 0,
        animation: state === "active" ? "pulse-dot 2s ease-in-out infinite" : "none",
      }}
    />
  );
}
