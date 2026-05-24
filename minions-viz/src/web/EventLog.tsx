import { useMemo, useState } from "react";
import type { AgentInfo, LogEntry, Message, Task } from "@shared/types";
import { roleBucket, agentShortTag } from "./roleIdentity";

interface Props {
  logs: LogEntry[];
  messages: Message[];
  tasks: Task[];
  agents: AgentInfo[];
}

type EventKind =
  | "message"
  | "log"
  | "task"
  | "bid"
  | "result"
  | "adjudication";

interface TimelineEntry {
  kind: EventKind;
  /** Sub-kind for filter display (e.g. "create", "bid_submitted", "bid_rejected"). */
  sub: string;
  ts: number;
  agent: string | null;
  target: string | null;
  title: string;
  detail: string;
  taskId: string | null;
  error?: string | null;
}

function parseTs(s: string): number {
  const ts = Date.parse(s);
  return Number.isNaN(ts) ? Date.now() : ts;
}

function fnNameSub(fn: string): { kind: EventKind; sub: string } {
  // Map admin-log fn_name → semantic event class. The EACN3 admin log uses
  // verb names that don't all match our 5-bucket taxonomy, so we coalesce
  // here. Anything we don't recognise stays as a generic "log".
  const f = fn.toLowerCase();
  if (f === "create_task") return { kind: "task", sub: "create" };
  if (f === "update_task" || f === "update_deadline")
    return { kind: "task", sub: "update" };
  if (f === "close_task") return { kind: "task", sub: "close" };
  if (f === "reject_task") return { kind: "task", sub: "reject" };
  if (f === "submit_bid") return { kind: "bid", sub: "submit" };
  if (f === "accept_bid") return { kind: "bid", sub: "accept" };
  if (f === "reject_bid") return { kind: "bid", sub: "reject" };
  if (f === "submit_result") return { kind: "result", sub: "submit" };
  if (f === "select_result") return { kind: "result", sub: "select" };
  if (f === "adjudicate" || f === "create_adjudication_task")
    return { kind: "adjudication", sub: "create" };
  if (f === "relay_message") return { kind: "message", sub: "send" };
  return { kind: "log", sub: fn };
}

function logToEntry(l: LogEntry): TimelineEntry {
  const { kind, sub } = fnNameSub(l.fn_name);
  let detail = "";
  if (l.error) {
    detail = `ERROR: ${l.error}`;
  } else if (kind === "bid" && l.args) {
    const a = l.args as Record<string, unknown>;
    detail = `conf=${a.confidence ?? "?"} price=${a.price ?? "?"}`;
  } else if (kind === "result" && l.args) {
    const a = l.args as Record<string, unknown>;
    const content = a.content;
    detail =
      typeof content === "string"
        ? content.slice(0, 200)
        : JSON.stringify(content ?? a).slice(0, 200);
  } else if (kind === "task" && l.args) {
    const a = l.args as Record<string, unknown>;
    const c = a.content as Record<string, unknown> | undefined;
    detail =
      (typeof c?.description === "string"
        ? c.description
        : JSON.stringify(c ?? a)
      ).slice(0, 200);
  } else if (kind === "adjudication" && l.args) {
    const a = l.args as Record<string, unknown>;
    detail = `verdict=${a.verdict ?? "?"} score=${a.score ?? "?"}`;
  } else {
    detail = JSON.stringify(l.result ?? l.args ?? {}).slice(0, 200);
  }

  // For bid/result/adjudication events, the target is the task initiator's
  // hint — but admin logs don't carry that directly, so we leave target null
  // and just show the task id.
  return {
    kind,
    sub,
    ts: parseTs(l.timestamp),
    agent: l.agent_id,
    target: null,
    title: `${kind}:${sub}`,
    detail,
    taskId: l.task_id,
    error: l.error,
  };
}

function messageToEntry(m: Message): TimelineEntry {
  return {
    kind: "message",
    sub: "send",
    ts: parseTs(m.timestamp),
    agent: m.from_agent_id,
    target: m.to_agent_id,
    title: `message → ${m.to_agent_id}`,
    detail:
      typeof m.content === "string" ? m.content : JSON.stringify(m.content),
    taskId: m.task_id,
  };
}

const KIND_COLOR: Record<EventKind, string> = {
  message: "var(--role-writer)",
  task: "var(--role-noter)",
  bid: "var(--role-coder)",
  result: "var(--status-completed)",
  adjudication: "#fcd34d",
  log: "var(--muted)",
};

const KIND_GLYPH: Record<EventKind, string> = {
  message: "✉",
  task: "▦",
  bid: "⊕",
  result: "✓",
  adjudication: "⚖",
  log: "·",
};

const ALL_KINDS: EventKind[] = [
  "message",
  "task",
  "bid",
  "result",
  "adjudication",
  "log",
];

function toTimeline(
  logs: LogEntry[],
  messages: Message[],
  tasks: Task[],
): TimelineEntry[] {
  const out: TimelineEntry[] = [];
  for (const m of messages) out.push(messageToEntry(m));
  for (const l of logs) out.push(logToEntry(l));

  // Synthesise task-shape entries from current task state when the admin log
  // didn't surface them. This catches bids/results that arrive only via the
  // /api/tasks snapshot (e.g. backends without admin-log enabled).
  const seenTasks = new Set<string>();
  for (const e of out) if (e.taskId) seenTasks.add(`${e.kind}:${e.taskId}`);

  for (const t of tasks) {
    // Surface adjudication tasks even if no admin-log create entry exists.
    if (t.type === "adjudication" && !seenTasks.has(`adjudication:${t.id}`)) {
      out.push({
        kind: "adjudication",
        sub: "task",
        ts: parseTs((t.content as Record<string, unknown>)?.created_at as string ?? ""),
        agent: t.initiator_id,
        target: null,
        title: "adjudication:task",
        detail:
          (t.content as Record<string, unknown>)?.description as string ??
          JSON.stringify(t.content).slice(0, 200),
        taskId: t.id,
      });
    }
    for (const b of t.bids ?? []) {
      const id = `bid:${t.id}:${b.agent_id}:${b.status}`;
      if (seenTasks.has(id)) continue;
      seenTasks.add(id);
      out.push({
        kind: "bid",
        sub: b.status,
        ts: Date.now(),
        agent: b.agent_id,
        target: t.initiator_id,
        title: `bid:${b.status}`,
        detail: `task ${t.id.slice(0, 8)} · conf ${b.confidence.toFixed(2)} · price ${b.price}`,
        taskId: t.id,
      });
    }
    for (const r of t.results ?? []) {
      const id = `result:${t.id}:${r.agent_id}`;
      if (seenTasks.has(id)) continue;
      seenTasks.add(id);
      out.push({
        kind: "result",
        sub: r.selected ? "selected" : "submit",
        ts: Date.now(),
        agent: r.agent_id,
        target: t.initiator_id,
        title: r.selected ? "result:selected" : "result:submit",
        detail:
          typeof r.content === "string"
            ? r.content.slice(0, 200)
            : JSON.stringify(r.content).slice(0, 200),
        taskId: t.id,
      });
      for (const adj of r.adjudications ?? []) {
        out.push({
          kind: "adjudication",
          sub: "verdict",
          ts: Date.now(),
          agent: adj.adjudicator_id,
          target: r.agent_id,
          title: `adjudication:${adj.verdict}`,
          detail: `score ${adj.score.toFixed(2)} for ${r.agent_id.slice(0, 8)}`,
          taskId: t.id,
        });
      }
    }
  }

  out.sort((a, b) => b.ts - a.ts);
  return out;
}

export default function EventLog({ logs, messages, tasks, agents }: Props) {
  const [filter, setFilter] = useState<string>("");
  const [enabled, setEnabled] = useState<Set<EventKind>>(() => new Set(ALL_KINDS));
  const [onlyErrors, setOnlyErrors] = useState(false);

  const nameFor = (id: string | null) =>
    id ? (agents.find((a) => a.agent_id === id)?.name ?? id) : "system";

  const all = useMemo(
    () => toTimeline(logs, messages, tasks),
    [logs, messages, tasks],
  );

  const counts = useMemo(() => {
    const m: Record<EventKind, number> = {
      message: 0,
      task: 0,
      bid: 0,
      result: 0,
      adjudication: 0,
      log: 0,
    };
    for (const e of all) m[e.kind] += 1;
    return m;
  }, [all]);

  const filtered = useMemo(() => {
    const needle = filter.toLowerCase();
    return all.filter((e) => {
      if (!enabled.has(e.kind)) return false;
      if (onlyErrors && !e.error) return false;
      if (!needle) return true;
      return (
        (e.agent || "").toLowerCase().includes(needle) ||
        (e.target || "").toLowerCase().includes(needle) ||
        e.title.toLowerCase().includes(needle) ||
        e.sub.toLowerCase().includes(needle) ||
        (e.detail || "").toLowerCase().includes(needle) ||
        (e.taskId || "").toLowerCase().includes(needle)
      );
    });
  }, [all, filter, enabled, onlyErrors]);

  const toggleKind = (k: EventKind) => {
    setEnabled((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
  };

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
          <div className="event-kind-chips">
            {ALL_KINDS.map((k) => (
              <button
                key={k}
                className={`event-kind-chip${enabled.has(k) ? " active" : ""}`}
                style={{ ["--chip-color" as string]: KIND_COLOR[k] }}
                onClick={() => toggleKind(k)}
                title={`${k} · ${counts[k]}`}
              >
                <span className="glyph">{KIND_GLYPH[k]}</span>
                <span>{k}</span>
                <span className="ct">{counts[k]}</span>
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
        {filtered.length === 0 && (
          <div className="empty">No events match.</div>
        )}
        {filtered.map((e, i) => {
          const fromB = e.agent ? roleBucket(e.agent) : null;
          const toB = e.target ? roleBucket(e.target) : null;
          const when = new Date(e.ts).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          });
          return (
            <div
              key={i}
              className={`event-row ${e.kind}${e.error ? " err" : ""}`}
            >
              <span className="ev-time">{when}</span>
              <span
                className="ev-kind"
                style={{ color: KIND_COLOR[e.kind] }}
              >
                {KIND_GLYPH[e.kind]} {e.kind}
              </span>
              <span className="ev-sub">{e.sub}</span>
              <span className="ev-from">
                {fromB && (
                  <span style={{ color: fromB.color }}>
                    {agentShortTag(e.agent!)}{" "}
                  </span>
                )}
                <span style={{ color: "var(--muted)" }}>{nameFor(e.agent)}</span>
              </span>
              {e.target && (
                <span className="ev-to">
                  →{" "}
                  <span style={{ color: toB?.color ?? "var(--text-2)" }}>
                    {e.target.length > 16
                      ? agentShortTag(e.target)
                      : e.target}
                  </span>
                  <span style={{ color: "var(--muted)", marginLeft: 4 }}>
                    {nameFor(e.target)}
                  </span>
                </span>
              )}
              {e.taskId && (
                <span className="ev-tid" title={e.taskId}>
                  #{e.taskId.slice(0, 8)}
                </span>
              )}
              <span className="ev-detail" title={e.detail}>
                {e.error ? (
                  <span style={{ color: "var(--status-error)" }}>✗ </span>
                ) : null}
                {e.detail}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
