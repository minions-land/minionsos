import { useState } from "react";
import { Rows, TreeStructure, ListChecks } from "@phosphor-icons/react";
import { useLimitPref } from "../../hooks/useLimitPref";
import { shortId, statusBadge, statusLabel, truncate } from "../../utils/format";
import EmptyState from "../../components/EmptyState";
import TaskTree from "./TaskTree";
import type { AgentInfo, Task, TaskStatus } from "@shared/types";

interface Props {
  tasks: Task[];
  agents: AgentInfo[];
  onSelect: (id: string) => void;
}

type View = "board" | "tree";

const COLUMNS: { key: TaskStatus; label: string }[] = [
  { key: "unclaimed", label: "Unclaimed" },
  { key: "bidding", label: "Bidding" },
  { key: "awaiting_retrieval", label: "In Progress" },
  { key: "completed", label: "Completed" },
];

function taskDescription(t: Task): string {
  if (typeof t.content?.description === "string") return t.content.description;
  if (typeof t.content?.content === "string") return t.content.content;
  const s = JSON.stringify(t.content);
  return s === "{}" ? "(no description)" : s;
}

export default function TasksPanel({ tasks, agents, onSelect }: Props) {
  const [view, setView] = useState<View>("board");
  const [limit, setLimit, options] = useLimitPref("viz.limit.tasks", 50, [20, 50, 100]);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <div className="section-label" style={{ margin: 0 }}>Tasks</div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <select
            className="limit-select"
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
          >
            {options.map((o) => (
              <option key={o} value={o}>{o}</option>
            ))}
          </select>
          <div style={{ display: "flex", borderRadius: 6, overflow: "hidden", border: "1px solid var(--line)" }}>
            <button
              onClick={() => setView("board")}
              style={{
                padding: "4px 8px",
                background: view === "board" ? "var(--surface)" : "transparent",
                border: "none",
                color: view === "board" ? "var(--text)" : "var(--muted)",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 4,
                fontSize: 11,
              }}
            >
              <Rows size={14} /> Board
            </button>
            <button
              onClick={() => setView("tree")}
              style={{
                padding: "4px 8px",
                background: view === "tree" ? "var(--surface)" : "transparent",
                border: "none",
                color: view === "tree" ? "var(--text)" : "var(--muted)",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 4,
                fontSize: 11,
              }}
            >
              <TreeStructure size={14} /> Tree
            </button>
          </div>
        </div>
      </div>

      {view === "tree" ? (
        <TaskTree tasks={tasks} onSelect={onSelect} />
      ) : tasks.length === 0 ? (
        <EmptyState icon={ListChecks} message="No tasks yet" />
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
          {COLUMNS.map((col) => {
            const colTasks = tasks
              .filter((t) => t.status === col.key)
              .sort((a, b) => (b.id > a.id ? 1 : -1))
              .slice(0, limit);
            return (
              <div key={col.key}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
                  <span style={{ fontSize: 11, fontWeight: 500, color: "var(--text-2)" }}>{col.label}</span>
                  <span className="badge" style={{ fontSize: 9 }}>{colTasks.length}</span>
                </div>
                <div className="scroll-region" style={{ maxHeight: 320, display: "flex", flexDirection: "column", gap: 4 }}>
                  {colTasks.map((t) => (
                    <button
                      key={t.id}
                      onClick={() => onSelect(t.id)}
                      className="surface-card"
                      style={{
                        textAlign: "left",
                        cursor: "pointer",
                        padding: "8px 10px",
                        width: "100%",
                        background: "var(--panel-bg)",
                        border: "1px solid var(--line)",
                        borderRadius: 6,
                      }}
                    >
                      <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>
                        {shortId(t.id)}
                      </div>
                      <div style={{ fontSize: 11, color: "var(--text)", marginTop: 3, lineHeight: 1.3 }}>
                        {truncate(taskDescription(t), 80)}
                      </div>
                      <div style={{ display: "flex", gap: 4, marginTop: 5, flexWrap: "wrap" }}>
                        <span className={`pill ${statusBadge(t.status)}`} style={{ fontSize: 9 }}>
                          {statusLabel(t.status)}
                        </span>
                        {t.domains.slice(0, 2).map((d) => (
                          <span key={d} className="pill" style={{ fontSize: 9 }}>{d}</span>
                        ))}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
