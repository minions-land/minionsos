import { useEffect } from "react";
import { X } from "@phosphor-icons/react";
import type { Task, AgentInfo } from "@shared/types";
import { shortId, statusLabel, statusColor, timeAgo } from "../utils/format";

interface Props {
  open: boolean;
  taskId: string | null;
  tasks: Task[];
  agents: AgentInfo[];
  onClose: () => void;
  onSelectAgent: (id: string) => void;
}

export default function TaskDetailModal({ open, taskId, tasks, agents, onClose, onSelectAgent }: Props) {
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open || !taskId) return null;
  const task = tasks.find((t) => t.id === taskId);
  if (!task) return null;

  const agentName = (id: string) => agents.find((a) => a.agent_id === id)?.name || shortId(id);
  const desc = typeof task.content.description === "string"
    ? task.content.description
    : JSON.stringify(task.content, 2);

  const statusBg: Record<string, string> = {
    unclaimed: "var(--status-unclaimed)",
    bidding: "var(--status-bidding)",
    awaiting_retrieval: "var(--status-active)",
    completed: "var(--status-completed)",
    no_one_able: "var(--status-error)",
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: "var(--z-modal)",
        display: "grid",
        placeItems: "center",
      }}
    >
      {/* Scrim */}
      <div
        onClick={onClose}
        style={{
          position: "absolute",
          inset: 0,
          background: "rgba(0,0,0,0.6)",
          animation: "fade-in 200ms var(--ease-out)",
        }}
      />

      {/* Modal */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Task detail"
        onClick={(e) => e.stopPropagation()}
        style={{
          position: "relative",
          width: "min(560px, 92vw)",
          maxHeight: "85vh",
          overflowY: "auto",
          background: "var(--panel-bg)",
          backdropFilter: "blur(16px)",
          WebkitBackdropFilter: "blur(16px)",
          border: "1px solid var(--line)",
          borderRadius: "var(--radius)",
          boxShadow: "var(--shadow-panel)",
          animation: "modal-in 250ms var(--ease-out)",
        }}
      >
        <style>{`
          @keyframes modal-in {
            from { opacity: 0; transform: scale(0.95); }
            to   { opacity: 1; transform: scale(1); }
          }
        `}</style>

        {/* Header */}
        <div style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "16px 20px",
          borderBottom: "1px solid var(--line)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{
              display: "inline-flex",
              alignItems: "center",
              padding: "2px 8px",
              borderRadius: "var(--radius-pill)",
              background: statusBg[task.status] || "var(--surface)",
              color: "#fff",
              fontFamily: "var(--font-mono)",
              fontSize: 10,
              fontWeight: 500,
              textTransform: "uppercase",
            }}>
              {statusLabel(task.status)}
            </span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)" }}>
              {shortId(task.id)}
            </span>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{
              width: 28, height: 28, display: "grid", placeItems: "center",
              borderRadius: "var(--radius-xs)", border: "1px solid var(--line)",
              background: "var(--surface)", color: "var(--muted)", cursor: "pointer",
            }}
          >
            <X size={14} />
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: "16px 20px", display: "flex", flexDirection: "column", gap: 16 }}>
          {/* ID */}
          <div>
            <div className="section-label" style={{ marginBottom: 4 }}>Task ID</div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-2)", wordBreak: "break-all" }}>
              {task.id}
            </div>
          </div>

          {/* Initiator + Assigned */}
          <div style={{ display: "flex", gap: 24 }}>
            <div>
              <div className="section-label" style={{ marginBottom: 4 }}>Initiator</div>
              <button
                onClick={() => onSelectAgent(task.initiator_id)}
                style={{ color: "var(--role-noter)", fontSize: 12, background: "none", border: "none", cursor: "pointer", fontFamily: "var(--font-mono)" }}
              >
                {agentName(task.initiator_id)}
              </button>
            </div>
            {task.bids.some((b) => b.status === "accepted" || b.status === "executing") && (
              <div>
                <div className="section-label" style={{ marginBottom: 4 }}>Assigned</div>
                {task.bids
                  .filter((b) => b.status === "accepted" || b.status === "executing")
                  .map((b) => (
                    <button
                      key={b.agent_id}
                      onClick={() => onSelectAgent(b.agent_id)}
                      style={{ color: "var(--role-noter)", fontSize: 12, background: "none", border: "none", cursor: "pointer", fontFamily: "var(--font-mono)" }}
                    >
                      {agentName(b.agent_id)}
                    </button>
                  ))}
              </div>
            )}
          </div>

          {/* Domains */}
          {task.domains.length > 0 && (
            <div>
              <div className="section-label" style={{ marginBottom: 6 }}>Domains</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                {task.domains.map((d) => (
                  <span key={d} className="pill">{d}</span>
                ))}
              </div>
            </div>
          )}

          {/* Description */}
          <div>
            <div className="section-label" style={{ marginBottom: 6 }}>Description</div>
            <div style={{
              fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-2)",
              whiteSpace: "pre-wrap", maxHeight: 200, overflowY: "auto",
              background: "var(--surface)", borderRadius: "var(--radius-xs)",
              padding: 12, border: "1px solid var(--line)",
            }}>
              {desc}
            </div>
          </div>

          {/* Subtasks */}
          {task.child_ids.length > 0 && (
            <div>
              <div className="section-label" style={{ marginBottom: 6 }}>Subtasks</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {task.child_ids.map((cid) => {
                  const child = tasks.find((t) => t.id === cid);
                  return (
                    <div key={cid} style={{
                      display: "flex", alignItems: "center", gap: 8,
                      padding: "6px 10px", borderRadius: "var(--radius-xs)",
                      background: "var(--surface)", border: "1px solid var(--line-soft)",
                    }}>
                      {child && <span className={`w-2 h-2 rounded-full ${statusColor(child.status)}`} />}
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>
                        {shortId(cid)}
                      </span>
                      {child && (
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted-2)", marginLeft: "auto" }}>
                          {statusLabel(child.status)}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Results */}
          {task.results.length > 0 && (
            <div>
              <div className="section-label" style={{ marginBottom: 6 }}>Results</div>
              {task.results.map((r) => (
                <div key={r.agent_id} style={{
                  padding: 10, borderRadius: "var(--radius-xs)",
                  background: "var(--surface)", border: `1px solid ${r.selected ? "var(--status-completed)" : "var(--line)"}`,
                  marginBottom: 6,
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                    <button
                      onClick={() => onSelectAgent(r.agent_id)}
                      style={{ color: "var(--role-noter)", fontSize: 11, background: "none", border: "none", cursor: "pointer", fontFamily: "var(--font-mono)" }}
                    >
                      {agentName(r.agent_id)}
                    </button>
                    {r.selected && (
                      <span style={{
                        fontSize: 9, padding: "1px 6px", borderRadius: "var(--radius-pill)",
                        background: "var(--status-completed)", color: "#fff",
                      }}>
                        SELECTED
                      </span>
                    )}
                  </div>
                  <div style={{
                    fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-2)",
                    whiteSpace: "pre-wrap", maxHeight: 100, overflowY: "auto",
                  }}>
                    {typeof r.content === "string" ? r.content : JSON.stringify(r.content, null, 2)}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Timeline */}
          <div>
            <div className="section-label" style={{ marginBottom: 6 }}>Timeline</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, fontFamily: "var(--font-mono)", fontSize: 10 }}>
              {task.content.created_at && (
                <div style={{ color: "var(--muted)" }}>Created: <span style={{ color: "var(--text-2)" }}>{timeAgo(task.content.created_at as string)}</span></div>
              )}
              {task.bids.length > 0 && (
                <div style={{ color: "var(--muted)" }}>Bids: <span style={{ color: "var(--text-2)" }}>{task.bids.length}</span></div>
              )}
              {task.results.length > 0 && (
                <div style={{ color: "var(--muted)" }}>Results: <span style={{ color: "var(--text-2)" }}>{task.results.length}</span></div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
