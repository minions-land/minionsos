import { useState, useMemo, useRef, useEffect } from "react";
import { MagnifyingGlass, X } from "@phosphor-icons/react";
import type { Task, AgentInfo, LogEntry } from "@shared/types";
import { shortId, statusLabel, timeAgo } from "../utils/format";

interface Props {
  tasks: Task[];
  agents: AgentInfo[];
  logs: LogEntry[];
  onSelectAgent: (id: string) => void;
  onSelectTask: (id: string) => void;
  onClose: () => void;
}

type ResultItem =
  | { kind: "agent"; agent: AgentInfo }
  | { kind: "task"; task: Task }
  | { kind: "log"; log: LogEntry; index: number };

export default function GlobalSearch({ tasks, agents, logs, onSelectAgent, onSelectTask, onClose }: Props) {
  const [query, setQuery] = useState("");
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  const results = useMemo<ResultItem[]>(() => {
    const q = query.trim().toLowerCase();
    if (q.length < 2) return [];
    const items: ResultItem[] = [];

    for (const a of agents) {
      if (
        a.name.toLowerCase().includes(q) ||
        a.agent_id.toLowerCase().includes(q) ||
        a.domains.some((d) => d.toLowerCase().includes(q)) ||
        a.description.toLowerCase().includes(q)
      ) {
        items.push({ kind: "agent", agent: a });
      }
      if (items.length >= 30) break;
    }

    for (const tk of tasks) {
      const desc = typeof tk.content.description === "string" ? tk.content.description : "";
      if (
        tk.id.toLowerCase().includes(q) ||
        desc.toLowerCase().includes(q) ||
        tk.domains.some((d) => d.toLowerCase().includes(q))
      ) {
        items.push({ kind: "task", task: tk });
      }
      if (items.length >= 60) break;
    }

    for (let i = 0; i < logs.length && items.length < 80; i++) {
      const l = logs[i];
      if (
        l.fn_name.toLowerCase().includes(q) ||
        l.task_id?.toLowerCase().includes(q) ||
        l.agent_id?.toLowerCase().includes(q)
      ) {
        items.push({ kind: "log", log: l, index: i });
      }
    }

    return items;
  }, [query, agents, tasks, logs]);

  useEffect(() => { setActiveIdx(0); }, [results]);

  function handleSelect(item: ResultItem) {
    if (item.kind === "agent") onSelectAgent(item.agent.agent_id);
    else if (item.kind === "task") onSelectTask(item.task.id);
    else if (item.kind === "log") {
      if (item.log.task_id) onSelectTask(item.log.task_id);
      else if (item.log.agent_id) onSelectAgent(item.log.agent_id);
    }
    onClose();
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && results[activeIdx]) {
      e.preventDefault();
      handleSelect(results[activeIdx]);
    }
  }

  // Group results for display
  const agentResults = results.filter((r): r is Extract<ResultItem, { kind: "agent" }> => r.kind === "agent");
  const taskResults = results.filter((r): r is Extract<ResultItem, { kind: "task" }> => r.kind === "task");
  const logResults = results.filter((r): r is Extract<ResultItem, { kind: "log" }> => r.kind === "log");

  let flatIdx = -1;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: "var(--z-modal)",
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "center",
        paddingTop: 80,
      }}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Global search"
    >
      {/* Scrim */}
      <div style={{ position: "absolute", inset: 0, background: "rgba(0,0,0,0.5)" }} />

      {/* Modal */}
      <div
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
        style={{
          position: "relative",
          width: "min(540px, 92vw)",
          background: "var(--panel-bg)",
          backdropFilter: "blur(16px)",
          WebkitBackdropFilter: "blur(16px)",
          border: "1px solid var(--line)",
          borderRadius: "var(--radius)",
          boxShadow: "var(--shadow-panel)",
          overflow: "hidden",
          animation: "modal-in 250ms var(--ease-out)",
        }}
      >
        <style>{`
          @keyframes modal-in {
            from { opacity: 0; transform: scale(0.95); }
            to   { opacity: 1; transform: scale(1); }
          }
        `}</style>

        {/* Input */}
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "14px 16px",
          borderBottom: "1px solid var(--line)",
        }}>
          <MagnifyingGlass size={16} style={{ color: "var(--muted)", flexShrink: 0 }} />
          <input
            ref={inputRef}
            type="text"
            placeholder="Search agents, tasks, messages..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search"
            style={{
              flex: 1,
              background: "transparent",
              border: "none",
              outline: "none",
              color: "var(--text)",
              fontFamily: "var(--font-mono)",
              fontSize: 13,
            }}
          />
          <span className="kbd">ESC</span>
        </div>

        {/* Results */}
        <div style={{ maxHeight: 400, overflowY: "auto" }} role="listbox" aria-label="Search results">
          {query.length < 2 && (
            <div style={{ padding: 24, textAlign: "center", fontSize: 11, color: "var(--muted)" }}>
              Type at least 2 characters to search.
            </div>
          )}

          {query.length >= 2 && results.length === 0 && (
            <div style={{ padding: 32, textAlign: "center" }}>
              <MagnifyingGlass size={28} weight="thin" style={{ color: "var(--muted)", opacity: 0.4, marginBottom: 8 }} />
              <div style={{ fontSize: 11, color: "var(--muted)" }}>No results found.</div>
            </div>
          )}

          {/* Agents group */}
          {agentResults.length > 0 && (
            <div>
              <div style={{
                padding: "8px 16px 4px",
                fontFamily: "var(--font-mono)",
                fontSize: 9,
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                color: "var(--muted)",
              }}>
                Agents
              </div>
              {agentResults.map((item) => {
                flatIdx++;
                const isActive = flatIdx === activeIdx;
                const a = item.agent;
                return (
                  <button
                    key={`a-${a.agent_id}`}
                    onClick={() => handleSelect(item)}
                    role="option"
                    aria-selected={isActive}
                    style={{
                      width: "100%",
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      padding: "8px 16px",
                      border: "none",
                      background: isActive ? "var(--surface)" : "transparent",
                      color: "var(--text-2)",
                      fontSize: 12,
                      cursor: "pointer",
                      textAlign: "left",
                    }}
                  >
                    <span className="pill" style={{ fontSize: 9 }}>Agent</span>
                    <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.name}</span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>{shortId(a.agent_id)}</span>
                  </button>
                );
              })}
            </div>
          )}

          {/* Tasks group */}
          {taskResults.length > 0 && (
            <div>
              <div style={{
                padding: "8px 16px 4px",
                fontFamily: "var(--font-mono)",
                fontSize: 9,
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                color: "var(--muted)",
              }}>
                Tasks
              </div>
              {taskResults.map((item) => {
                flatIdx++;
                const isActive = flatIdx === activeIdx;
                const tk = item.task;
                const desc = typeof tk.content.description === "string" ? tk.content.description : "";
                return (
                  <button
                    key={`t-${tk.id}`}
                    onClick={() => handleSelect(item)}
                    role="option"
                    aria-selected={isActive}
                    style={{
                      width: "100%",
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      padding: "8px 16px",
                      border: "none",
                      background: isActive ? "var(--surface)" : "transparent",
                      color: "var(--text-2)",
                      fontSize: 12,
                      cursor: "pointer",
                      textAlign: "left",
                    }}
                  >
                    <span className="badge" style={{ background: "var(--status-bidding)", color: "#fff", fontSize: 9 }}>
                      {statusLabel(tk.status)}
                    </span>
                    <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {desc || shortId(tk.id)}
                    </span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>{shortId(tk.id)}</span>
                  </button>
                );
              })}
            </div>
          )}

          {/* Messages/Logs group */}
          {logResults.length > 0 && (
            <div>
              <div style={{
                padding: "8px 16px 4px",
                fontFamily: "var(--font-mono)",
                fontSize: 9,
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                color: "var(--muted)",
              }}>
                Messages
              </div>
              {logResults.map((item) => {
                flatIdx++;
                const isActive = flatIdx === activeIdx;
                const l = item.log;
                return (
                  <button
                    key={`l-${item.index}`}
                    onClick={() => handleSelect(item)}
                    role="option"
                    aria-selected={isActive}
                    style={{
                      width: "100%",
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      padding: "8px 16px",
                      border: "none",
                      background: isActive ? "var(--surface)" : "transparent",
                      color: "var(--text-2)",
                      fontSize: 12,
                      cursor: "pointer",
                      textAlign: "left",
                    }}
                  >
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--role-noter)" }}>{l.fn_name}</span>
                    {l.task_id && <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>{shortId(l.task_id)}</span>}
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted-2)", marginLeft: "auto" }}>
                      {timeAgo(l.timestamp)}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        {query.length >= 2 && results.length > 0 && (
          <div style={{
            padding: "8px 16px",
            borderTop: "1px solid var(--line)",
            fontFamily: "var(--font-mono)",
            fontSize: 10,
            color: "var(--muted)",
          }}>
            {results.length} results · ↑↓ navigate · ↵ select
          </div>
        )}
      </div>
    </div>
  );
}
