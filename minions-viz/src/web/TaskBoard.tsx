import { useMemo, useState } from "react";
import type { AgentInfo, Task, TaskStatus } from "@shared/types";
import { roleBucket, agentShortTag } from "./roleIdentity";

interface Props {
  tasks: Task[];
  agents: AgentInfo[];
  onSelectTask?: (id: string) => void;
}

const COLS: { key: TaskStatus; label: string; tint: string }[] = [
  { key: "unclaimed", label: "Unclaimed", tint: "var(--status-unclaimed)" },
  { key: "bidding", label: "Bidding", tint: "var(--status-bidding)" },
  { key: "awaiting_retrieval", label: "In progress", tint: "var(--status-progress)" },
  { key: "completed", label: "Completed", tint: "var(--status-completed)" },
];

function taskDescription(t: Task): string {
  const c = t.content as Record<string, unknown>;
  if (typeof c?.description === "string") return c.description as string;
  if (typeof c?.content === "string") return c.content as string;
  const s = JSON.stringify(t.content);
  return s === "{}" ? "(no description)" : s;
}

function taskCreatedAt(t: Task): number | null {
  const c = t.content as Record<string, unknown>;
  for (const k of ["created_at", "created", "timestamp"]) {
    const v = c?.[k];
    if (typeof v === "string") {
      const ts = Date.parse(v);
      if (!Number.isNaN(ts)) return ts;
    }
    if (typeof v === "number") return v;
  }
  return null;
}

function timeAgo(tsMs: number | null): string {
  if (tsMs == null) return "—";
  const secs = Math.max(0, Math.floor((Date.now() - tsMs) / 1000));
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h`;
  return `${Math.floor(secs / 86400)}d`;
}

function deadlineFmt(d: string | null): { text: string; overdue: boolean } {
  if (!d) return { text: "", overdue: false };
  const ts = Date.parse(d);
  if (Number.isNaN(ts)) return { text: "", overdue: false };
  const now = Date.now();
  const diff = ts - now;
  const overdue = diff < 0;
  const absMin = Math.abs(diff) / 60000;
  let text: string;
  if (absMin < 60) text = `${Math.round(absMin)}m`;
  else if (absMin < 1440) text = `${Math.round(absMin / 60)}h`;
  else text = `${Math.round(absMin / 1440)}d`;
  return { text: overdue ? `overdue ${text}` : `due in ${text}`, overdue };
}

export default function TaskBoard({
  tasks,
  agents,
  onSelectTask,
}: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const byParent = useMemo(() => {
    const m = new Map<string, Task[]>();
    const top: Task[] = [];
    for (const t of tasks) {
      if (t.parent_id) {
        const arr = m.get(t.parent_id) ?? [];
        arr.push(t);
        m.set(t.parent_id, arr);
      } else {
        top.push(t);
      }
    }
    for (const arr of m.values()) arr.sort((a, b) => (b.id > a.id ? 1 : -1));
    return { m, top };
  }, [tasks]);

  const byCol = useMemo(() => {
    const m = new Map<TaskStatus, Task[]>();
    for (const col of COLS) m.set(col.key, []);
    for (const t of byParent.top) {
      const arr = m.get(t.status);
      if (arr) arr.push(t);
    }
    for (const arr of m.values()) arr.sort((a, b) => (b.id > a.id ? 1 : -1));
    return m;
  }, [byParent]);

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const renderCard = (t: Task, depth = 0) => {
    const kids = byParent.m.get(t.id) ?? [];
    const hasKids = kids.length > 0;
    const bucket = roleBucket(t.initiator_id);
    const iTag = (() => {
      const a = agents.find((x) => x.agent_id === t.initiator_id);
      return a ? agentShortTag(a.agent_id) : t.initiator_id.slice(0, 6);
    })();
    const ddl = deadlineFmt(t.deadline);
    const age = timeAgo(taskCreatedAt(t));
    const isOpen = expanded.has(t.id);

    return (
      <div key={t.id} style={{ marginLeft: depth === 0 ? 0 : 12 }}>
        <div
          className="task-card"
          style={{ borderLeftColor: bucket.color }}
          onClick={() => onSelectTask?.(t.id)}
        >
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              {hasKids && (
                <button
                  className="chip"
                  onClick={(e) => {
                    e.stopPropagation();
                    toggle(t.id);
                  }}
                  style={{
                    height: 18, padding: "0 6px",
                    fontSize: 10, borderRadius: 4,
                  }}
                  title={isOpen ? "Collapse subtasks" : "Expand subtasks"}
                >
                  {isOpen ? "▾" : "▸"} {kids.length}
                </button>
              )}
              <span className="tid">#{t.id.slice(0, 10)}</span>
            </div>
            <span className="tag" style={{ color: bucket.color }}>{iTag}</span>
          </div>

          <div className="tdesc">{taskDescription(t)}</div>

          <div className="tags">
            {t.domains.slice(0, 3).map((d) => (
              <span key={d} className="tag">{d}</span>
            ))}
            {t.type === "adjudication" && (
              <span className="tag" style={{ color: "#fcd34d", borderColor: "rgba(252,211,77,0.4)" }}>adj</span>
            )}
            {t.bids?.length > 0 && (
              <span className="tag">{t.bids.length} bids</span>
            )}
          </div>

          <div className="task-meta">
            <span title="Age">◷ {age}</span>
            {ddl.text && (
              <span style={{ color: ddl.overdue ? "var(--status-error)" : "var(--muted)" }}>
                ⏱ {ddl.text}
              </span>
            )}
            {t.budget > 0 && (
              <span title="Budget">₿ {t.remaining_budget ?? t.budget}/{t.budget}</span>
            )}
          </div>
        </div>
        {isOpen && kids.map((c) => renderCard(c, depth + 1))}
      </div>
    );
  };

  return (
    <div className="task-board">
      {COLS.map((col) => {
        const list = byCol.get(col.key) ?? [];
        return (
          <div key={col.key} className="task-col">
            <div className="task-col-header">
              <div className="task-col-title" style={{ color: col.tint }}>
                <span className="tint" style={{ background: col.tint }} />
                {col.label}
              </div>
              <div className="task-col-count">{list.length}</div>
            </div>
            <div className="task-col-scroll">
              {list.length === 0 && (
                <div className="empty" style={{ padding: "16px 0" }}>empty</div>
              )}
              {list.map((t) => renderCard(t, 0))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
