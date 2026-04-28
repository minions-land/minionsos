import { Users, ListChecks, CheckCircle, CircleDashed, ChatDots, Plugs } from "@phosphor-icons/react";
import type { ComponentType } from "react";
import type { IconProps } from "@phosphor-icons/react";
import type { AgentInfo, Task } from "@shared/types";

interface Props {
  agents: AgentInfo[];
  tasks: Task[];
  messageCount: number;
  connected: boolean;
}

interface Metric {
  icon: ComponentType<IconProps>;
  label: string;
  value: string | number;
  color: string;
}

export default function MetricBar({ agents, tasks, messageCount, connected }: Props) {
  const metrics: Metric[] = [
    {
      icon: Users,
      label: "Agents Online",
      value: agents.length,
      color: "var(--role-gru)",
    },
    {
      icon: ListChecks,
      label: "Total Tasks",
      value: tasks.length,
      color: "var(--role-coder)",
    },
    {
      icon: CheckCircle,
      label: "Completed",
      value: tasks.filter((t) => t.status === "completed").length,
      color: "var(--status-completed)",
    },
    {
      icon: CircleDashed,
      label: "Open",
      value: tasks.filter((t) => t.status === "unclaimed" || t.status === "bidding").length,
      color: "var(--status-unclaimed)",
    },
    {
      icon: ChatDots,
      label: "Messages",
      value: messageCount,
      color: "var(--role-writer)",
    },
    {
      icon: Plugs,
      label: "Backend",
      value: connected ? "UP" : "DOWN",
      color: connected ? "var(--status-completed)" : "var(--status-error)",
    },
  ];

  return (
    <div className="grid grid-cols-3 lg:grid-cols-6 gap-3">
      {metrics.map((m, i) => (
        <div
          key={m.label}
          className="metric-card animate-fade-in"
          style={{ animationDelay: `${i * 50}ms`, animationFillMode: "backwards" }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <m.icon size={22} weight="duotone" style={{ color: m.color, flexShrink: 0 }} />
            <div>
              <div
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 22,
                  fontWeight: 600,
                  color: "var(--text)",
                  lineHeight: 1.1,
                }}
              >
                {m.value}
              </div>
              <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 2 }}>{m.label}</div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
