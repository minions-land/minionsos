import { useMemo, useState } from "react";
import type { AgentInfo, Task, TaskStatus } from "@shared/types";
import { roleBucket, agentShortTag } from "./roleIdentity";

interface Props {
  tasks: Task[];
  agents: AgentInfo[];
}

interface Column {
  key: TaskStatus | "adjudication";
  label: string;
  tint: string;
  /** Predicate: is this task a member of this column? */
  match: (t: Task) => boolean;
}

const COLS: Column[] = [
  {
    key: "unclaimed",
    label: "Unclaimed",
    tint: "var(--status-unclaimed)",
    match: (t) => t.type !== "adjudication" && t.status === "unclaimed",
  },
  {
    key: "bidding",
    label: "Bidding",
    tint: "var(--status-bidding)",
    match: (t) => t.type !== "adjudication" && t.status === "bidding",
  },
  {
    key: "awaiting_retrieval",
    label: "In progress",
    tint: "var(--status-progress)",
    match: (t) => t.type !== "adjudication" && t.status === "awaiting_retrieval",
  },
  {
    key: "completed",
    label: "Completed",
    tint: "var(--status-completed)",
    match: (t) => t.type !== "adjudication" && t.status === "completed",
  },
  {
    key: "adjudication",
    label: "Adjudication",
    tint: "#fcd34d",
    match: (t) => t.type === "adjudication",
  },
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

export default function TaskBoard({ tasks, agents }: Props) {
  const [expandedSubtasks, setExpandedSubtasks] = useState<Set<string>>(new Set());
  const [detailTaskId, setDetailTaskId] = useState<string | null>(null);

  const nameFor = (id: string) =>
    agents.find((a) => a.agent_id === id)?.name || id;

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
    const m = new Map<Column["key"], Task[]>();
    for (const col of COLS) m.set(col.key, []);
    for (const t of byParent.top) {
      for (const col of COLS) {
        if (col.match(t)) {
          m.get(col.key)!.push(t);
          break;
        }
      }
    }
    for (const arr of m.values()) arr.sort((a, b) => (b.id > a.id ? 1 : -1));
    return m;
  }, [byParent]);

  const detailTask = useMemo(
    () => (detailTaskId ? tasks.find((t) => t.id === detailTaskId) ?? null : null),
    [tasks, detailTaskId],
  );

  const toggle = (id: string) => {
    setExpandedSubtasks((prev) => {
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
    const isOpen = expandedSubtasks.has(t.id);
    const isActive = detailTaskId === t.id;

    return (
      <div key={t.id} style={{ marginLeft: depth === 0 ? 0 : 12 }}>
        <div
          className={"task-card" + (isActive ? " active" : "")}
          style={{ borderLeftColor: bucket.color }}
          onClick={() => setDetailTaskId(t.id)}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              gap: 8,
              alignItems: "center",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              {hasKids && (
                <button
                  className="chip"
                  onClick={(e) => {
                    e.stopPropagation();
                    toggle(t.id);
                  }}
                  style={{
                    height: 18,
                    padding: "0 6px",
                    fontSize: 10,
                    borderRadius: 4,
                  }}
                  title={isOpen ? "Collapse subtasks" : "Expand subtasks"}
                >
                  {isOpen ? "▾" : "▸"} {kids.length}
                </button>
              )}
              <span className="tid">#{t.id.slice(0, 10)}</span>
            </div>
            <span className="tag" style={{ color: bucket.color }}>
              {iTag}
            </span>
          </div>

          <div className="tdesc">{taskDescription(t)}</div>

          <div className="tags">
            {t.domains.slice(0, 3).map((d) => (
              <span key={d} className="tag">
                {d}
              </span>
            ))}
            {t.type === "adjudication" && (
              <span
                className="tag"
                style={{
                  color: "#fcd34d",
                  borderColor: "rgba(252,211,77,0.4)",
                }}
              >
                adj
              </span>
            )}
            {t.bids?.length > 0 && (
              <span className="tag">{t.bids.length} bids</span>
            )}
            {t.results?.length > 0 && (
              <span className="tag" style={{ color: "var(--status-completed)" }}>
                {t.results.length} results
              </span>
            )}
          </div>

          <div className="task-meta">
            <span title="Age">◷ {age}</span>
            {ddl.text && (
              <span
                style={{
                  color: ddl.overdue
                    ? "var(--status-error)"
                    : "var(--muted)",
                }}
              >
                ⏱ {ddl.text}
              </span>
            )}
            {t.budget > 0 && (
              <span title="Budget">
                ₿ {t.remaining_budget ?? t.budget}/{t.budget}
              </span>
            )}
          </div>
        </div>
        {isOpen && kids.map((c) => renderCard(c, depth + 1))}
      </div>
    );
  };

  return (
    <div className="task-board-wrap">
      <div
        className="task-board"
        style={{
          gridTemplateColumns: `repeat(${COLS.length}, minmax(0, 1fr))`,
        }}
      >
        {COLS.map((col) => {
          const list = byCol.get(col.key) ?? [];
          return (
            <div
              key={col.key}
              className={`task-col${col.key === "adjudication" ? " task-col-adj" : ""}`}
            >
              <div className="task-col-header">
                <div
                  className="task-col-title"
                  style={{ color: col.tint }}
                >
                  <span className="tint" style={{ background: col.tint }} />
                  {col.label}
                </div>
                <div className="task-col-count">{list.length}</div>
              </div>
              <div className="task-col-scroll">
                {list.length === 0 && (
                  <div className="empty" style={{ padding: "16px 0" }}>
                    empty
                  </div>
                )}
                {list.map((t) => renderCard(t, 0))}
              </div>
            </div>
          );
        })}
      </div>

      {detailTask && (
        <TaskDetailPanel
          task={detailTask}
          agents={agents}
          nameFor={nameFor}
          onClose={() => setDetailTaskId(null)}
        />
      )}
    </div>
  );
}

function TaskDetailPanel({
  task,
  agents,
  nameFor,
  onClose,
}: {
  task: Task;
  agents: AgentInfo[];
  nameFor: (id: string) => string;
  onClose: () => void;
}) {
  const bucket = roleBucket(task.initiator_id);
  const ddl = deadlineFmt(task.deadline);
  const desc = taskDescription(task);
  const isAdj = task.type === "adjudication";

  return (
    <div className="task-detail-panel" style={{ ["--accent-color" as string]: bucket.color }}>
      <div className="task-detail-header" style={{ borderBottomColor: `${bucket.color}55` }}>
        <span
          className="swatch"
          style={{ background: bucket.color, boxShadow: `0 0 10px ${bucket.color}` }}
        />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="task-detail-title">
            <span style={{ color: bucket.color }}>
              {isAdj ? "Adjudication" : "Task"}
            </span>
            <span className="task-detail-id"> #{task.id.slice(0, 16)}</span>
          </div>
          <div className="task-detail-sub">
            initiator: {agentShortTag(task.initiator_id)} ·{" "}
            {nameFor(task.initiator_id)}
          </div>
        </div>
        <span className={`badge ${task.status === "completed" ? "active" : "sleeping"}`}>
          {task.status}
        </span>
        <button className="task-detail-close" onClick={onClose}>
          ✕
        </button>
      </div>

      <div className="task-detail-body">
        <section>
          <h5>Description</h5>
          <div className="task-detail-desc">{desc}</div>
        </section>

        <section className="task-detail-grid">
          {task.domains.length > 0 && (
            <div>
              <h6>Domains</h6>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                {task.domains.map((d) => (
                  <span key={d} className="tag">
                    {d}
                  </span>
                ))}
              </div>
            </div>
          )}
          {task.deadline && (
            <div>
              <h6>Deadline</h6>
              <div
                style={{
                  color: ddl.overdue
                    ? "var(--status-error)"
                    : "var(--text-2)",
                }}
              >
                {task.deadline} {ddl.text && `(${ddl.text})`}
              </div>
            </div>
          )}
          {task.budget > 0 && (
            <div>
              <h6>Budget</h6>
              <div>
                {task.remaining_budget ?? task.budget} / {task.budget}
              </div>
            </div>
          )}
          {task.max_depth !== undefined && (
            <div>
              <h6>Depth</h6>
              <div>
                {task.depth} / {task.max_depth}
              </div>
            </div>
          )}
          {task.invited_agent_ids && task.invited_agent_ids.length > 0 && (
            <div style={{ gridColumn: "1 / -1" }}>
              <h6>Invited</h6>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                {task.invited_agent_ids.map((id) => (
                  <span key={id} className="tag">
                    {agentShortTag(id)}
                  </span>
                ))}
              </div>
            </div>
          )}
        </section>

        {task.bids?.length > 0 && (
          <section>
            <h5>Bids · {task.bids.length}</h5>
            <ul className="task-detail-list">
              {task.bids.map((b, i) => {
                const bb = roleBucket(b.agent_id);
                return (
                  <li key={i}>
                    <span style={{ color: bb.color, fontFamily: "var(--font-mono)" }}>
                      {agentShortTag(b.agent_id)}
                    </span>
                    <span style={{ color: "var(--muted)" }}>
                      {nameFor(b.agent_id)}
                    </span>
                    <span
                      className={`badge ${
                        b.status === "accepted" || b.status === "executing"
                          ? "active"
                          : b.status === "rejected"
                            ? "dismissed"
                            : "idle"
                      }`}
                    >
                      {b.status}
                    </span>
                    <span className="tag">conf {b.confidence.toFixed(2)}</span>
                    <span className="tag">price {b.price}</span>
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        {task.results?.length > 0 && (
          <section>
            <h5>Results · {task.results.length}</h5>
            {task.results.map((r, i) => {
              const rb = roleBucket(r.agent_id);
              return (
                <div key={i} className="task-detail-result">
                  <div className="task-detail-result-head">
                    <span style={{ color: rb.color, fontFamily: "var(--font-mono)" }}>
                      {agentShortTag(r.agent_id)}
                    </span>
                    <span style={{ color: "var(--muted)" }}>
                      {nameFor(r.agent_id)}
                    </span>
                    {r.selected && (
                      <span className="badge active" style={{ marginLeft: "auto" }}>
                        selected
                      </span>
                    )}
                  </div>
                  <pre className="task-detail-result-content">
                    {typeof r.content === "string"
                      ? r.content
                      : JSON.stringify(r.content, null, 2)}
                  </pre>
                  {r.adjudications?.length > 0 && (
                    <ul className="task-detail-list">
                      {r.adjudications.map((a, j) => (
                        <li key={j}>
                          <span style={{ color: "var(--muted)", fontFamily: "var(--font-mono)" }}>
                            {agentShortTag(a.adjudicator_id)}
                          </span>
                          <span>{a.verdict}</span>
                          <span
                            className="tag"
                            style={{
                              color:
                                a.score >= 0.6
                                  ? "var(--status-completed)"
                                  : a.score >= 0.3
                                    ? "var(--status-unclaimed)"
                                    : "var(--status-error)",
                            }}
                          >
                            score {a.score.toFixed(2)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </section>
        )}

        <section>
          <h5>Raw payload</h5>
          <pre className="task-detail-raw">
            {JSON.stringify(task.content, null, 2)}
          </pre>
        </section>
      </div>
    </div>
  );
}
