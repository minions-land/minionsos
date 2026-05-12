import type { AgentInfo, Task } from "@shared/types";

interface Props {
  agents: AgentInfo[];
  tasks: Task[];
  messageCount: number;
  connected: boolean;
}

export default function MetricHUD({ agents, tasks, messageCount, connected }: Props) {
  const completed = tasks.filter((t) => t.status === "completed").length;
  const open = tasks.filter(
    (t) => t.status === "unclaimed" || t.status === "bidding",
  ).length;
  const progress = tasks.filter((t) => t.status === "awaiting_retrieval").length;

  const cards = [
    { num: agents.length, lbl: "Agent instances", color: "var(--role-gru)" },
    { num: tasks.length, lbl: "Total tasks", color: "var(--role-coder)" },
    { num: open, lbl: "Open", color: "var(--status-unclaimed)" },
    { num: progress, lbl: "In progress", color: "var(--status-progress)" },
    { num: completed, lbl: "Completed", color: "var(--status-completed)" },
    { num: messageCount, lbl: "Messages", color: "var(--role-writer)" },
    {
      num: connected ? "UP" : "DOWN",
      lbl: "Backend",
      color: connected ? "var(--status-completed)" : "var(--status-error)",
    },
  ];

  return (
    <div className="metric-row">
      {cards.map((c) => (
        <div key={c.lbl} className="metric-card">
          <span className="bar" style={{ color: c.color as string }} />
          <div>
            <div className="num">{c.num}</div>
            <div className="lbl">{c.lbl}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
