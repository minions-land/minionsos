import { useMemo, useState } from "react";
import type { AgentInfo, LogEntry, Message } from "@shared/types";
import { roleBucket, agentShortTag } from "./roleIdentity";

interface Props {
  logs: LogEntry[];
  messages: Message[];
  agents: AgentInfo[];
}

interface TimelineEntry {
  kind: "message" | "log";
  ts: number;
  agent: string | null;
  target: string | null;
  title: string;
  detail: string;
  taskId: string | null;
  fn?: string;
  error?: string | null;
}

function parseTs(s: string): number {
  const ts = Date.parse(s);
  return Number.isNaN(ts) ? Date.now() : ts;
}

function toTimeline(logs: LogEntry[], messages: Message[]): TimelineEntry[] {
  const out: TimelineEntry[] = [];
  for (const m of messages) {
    out.push({
      kind: "message",
      ts: parseTs(m.timestamp),
      agent: m.from_agent_id,
      target: m.to_agent_id,
      title: `msg → ${m.to_agent_id}`,
      detail: typeof m.content === "string" ? m.content : JSON.stringify(m.content),
      taskId: m.task_id,
    });
  }
  for (const l of logs) {
    out.push({
      kind: "log",
      ts: parseTs(l.timestamp),
      agent: l.agent_id,
      target: null,
      title: l.fn_name,
      detail:
        l.error
          ? `ERROR: ${l.error}`
          : JSON.stringify(l.result ?? l.args ?? {}).slice(0, 240),
      taskId: l.task_id,
      fn: l.fn_name,
      error: l.error,
    });
  }
  out.sort((a, b) => b.ts - a.ts);
  return out;
}

export default function EventLog({ logs, messages, agents }: Props) {
  const [filter, setFilter] = useState<string>("");
  const [kind, setKind] = useState<"all" | "message" | "log">("all");
  const [onlyErrors, setOnlyErrors] = useState(false);

  const nameFor = (id: string | null) =>
    id ? (agents.find((a) => a.agent_id === id)?.name ?? id) : "system";

  const all = useMemo(() => toTimeline(logs, messages), [logs, messages]);
  const filtered = useMemo(() => {
    const needle = filter.toLowerCase();
    return all.filter((e) => {
      if (kind !== "all" && e.kind !== kind) return false;
      if (onlyErrors && !e.error) return false;
      if (!needle) return true;
      return (
        (e.agent || "").toLowerCase().includes(needle) ||
        (e.target || "").toLowerCase().includes(needle) ||
        e.title.toLowerCase().includes(needle) ||
        (e.detail || "").toLowerCase().includes(needle) ||
        (e.taskId || "").toLowerCase().includes(needle)
      );
    });
  }, [all, filter, kind, onlyErrors]);

  return (
    <div className="events-wrap">
      <div className="events-toolbar">
        <div style={{ display: "flex", gap: 8, alignItems: "center", flex: 1 }}>
          <input
            className="events-search"
            placeholder="filter by agent, task id, content…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </div>
        <div className="events-controls">
          <div className="seg">
            {(["all", "message", "log"] as const).map((k) => (
              <button
                key={k}
                className={k === kind ? "active" : ""}
                onClick={() => setKind(k)}
              >
                {k}
              </button>
            ))}
          </div>
          <label className="chip" style={{ gap: 6 }}>
            <input
              type="checkbox"
              checked={onlyErrors}
              onChange={(e) => setOnlyErrors(e.target.checked)}
              style={{ accentColor: "var(--status-error)" }}
            />
            errors only
          </label>
          <span className="chip" style={{ cursor: "default" }}>
            {filtered.length} / {all.length}
          </span>
        </div>
      </div>
      <div className="events-body">
        {filtered.length === 0 && <div className="empty">No events match.</div>}
        {filtered.map((e, i) => {
          const fromB = e.agent ? roleBucket(e.agent) : null;
          const toB = e.target ? roleBucket(e.target) : null;
          const when = new Date(e.ts).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          });
          return (
            <div key={i} className={`event-row ${e.kind}${e.error ? " err" : ""}`}>
              <span className="ev-time">{when}</span>
              <span
                className="ev-kind"
                style={{ color: e.kind === "message" ? "var(--role-writer)" : "var(--role-reviewer)" }}
              >
                {e.kind}
              </span>
              <span className="ev-from">
                {fromB && (
                  <span style={{ color: fromB.color }}>{agentShortTag(e.agent!)} </span>
                )}
                <span style={{ color: "var(--muted)" }}>{nameFor(e.agent)}</span>
              </span>
              {e.kind === "message" && e.target && (
                <span className="ev-to">
                  →{" "}
                  <span style={{ color: toB?.color ?? "var(--text-2)" }}>
                    {agentShortTag(e.target)}
                  </span>
                  <span style={{ color: "var(--muted)", marginLeft: 4 }}>
                    {nameFor(e.target)}
                  </span>
                </span>
              )}
              <span className="ev-title">
                {e.error ? <span style={{ color: "var(--status-error)" }}>✗ </span> : null}
                {e.title}
              </span>
              {e.taskId && <span className="ev-tid">{e.taskId.slice(0, 10)}</span>}
              <span className="ev-detail" title={e.detail}>
                {e.detail}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
