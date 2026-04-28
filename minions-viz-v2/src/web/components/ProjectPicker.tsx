import { selectProject, selectGru } from "../hooks/useStore";
import type { GruInfo, MosProject } from "@shared/types";
import { ArrowLeft } from "@phosphor-icons/react";
import { getRoleIdentity } from "../utils/roleIdentity";

interface Props {
  gru: GruInfo;
}

function statusBadgeColor(status: string): string {
  if (status === "active") return "var(--status-active)";
  if (status === "dormant") return "var(--status-unclaimed)";
  return "var(--muted)";
}

function primaryRoleColor(p: MosProject): string {
  const activeRole = p.active_roles.find((r) => r.state === "active");
  if (!activeRole) return "var(--line)";
  const identity = getRoleIdentity(activeRole.name);
  return identity.color;
}

export default function ProjectPicker({ gru }: Props) {
  const projects = gru.projects;
  const active = projects.filter((p) => p.status !== "closed");
  const closed = projects.filter((p) => p.status === "closed");

  return (
    <div style={{
      position: "absolute",
      inset: 0,
      overflow: "auto",
      padding: 32,
      background: "var(--bg-space)",
    }}>
      <div style={{ maxWidth: 900, margin: "0 auto" }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 28 }}>
          <div>
            <div className="section-label" style={{ marginBottom: 4 }}>Gru · {gru.label}</div>
            <h1 style={{ fontSize: 24, fontWeight: 700, color: "var(--text)", margin: 0 }}>Projects</h1>
            <p style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)", marginTop: 4 }}>
              {gru.rootPath}
            </p>
          </div>
          <button
            onClick={() => selectGru(null)}
            style={{
              display: "flex", alignItems: "center", gap: 5,
              padding: "6px 12px", borderRadius: "var(--radius-pill)",
              border: "1px solid var(--line)", background: "var(--surface)",
              color: "var(--muted)", fontSize: 11, cursor: "pointer",
              transition: `border-color 150ms var(--ease-out)`,
            }}
          >
            <ArrowLeft size={12} />
            Switch Gru
          </button>
        </div>

        {projects.length === 0 && (
          <div className="surface-card" style={{ padding: 40, textAlign: "center" }}>
            <div className="empty-state">
              <p style={{ color: "var(--muted)" }}>No projects in this Gru yet.</p>
            </div>
          </div>
        )}

        {/* Active / Dormant */}
        {active.length > 0 && (
          <>
            <div className="section-label" style={{ marginBottom: 12 }}>Active / Dormant</div>
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))",
              gap: 14,
              marginBottom: 32,
            }}>
              {active.map((p, idx) => (
                <ProjectCard key={p.port} p={p} idx={idx} />
              ))}
            </div>
          </>
        )}

        {/* Closed */}
        {closed.length > 0 && (
          <>
            <div className="section-label" style={{ marginBottom: 12 }}>Closed</div>
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))",
              gap: 14,
              opacity: 0.6,
            }}>
              {closed.map((p, idx) => (
                <ProjectCard key={p.port} p={p} idx={idx + active.length} />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function ProjectCard({ p, idx }: { p: MosProject; idx: number }) {
  const roleColor = primaryRoleColor(p);
  const activeRoles = p.active_roles.filter((r) => r.state !== "dismissed").length;

  return (
    <button
      onClick={() => selectProject(p.port)}
      className="animate-fade-in"
      style={{
        animationDelay: `${idx * 80}ms`,
        animationFillMode: "both",
        textAlign: "left",
        padding: 18,
        borderRadius: "var(--radius-sm)",
        border: "1px solid var(--line)",
        borderLeft: `3px solid ${p.status === "active" ? roleColor : "var(--line)"}`,
        background: "var(--panel-bg)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        boxShadow: "var(--shadow-panel)",
        cursor: "pointer",
        transition: `border-color 200ms var(--ease-out), box-shadow 200ms var(--ease-out)`,
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLElement).style.borderColor = "rgba(6,182,212,0.3)";
        (e.currentTarget as HTMLElement).style.boxShadow = "var(--shadow-glow-sm)";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLElement).style.borderColor = "var(--line)";
        (e.currentTarget as HTMLElement).style.borderLeftColor = p.status === "active" ? roleColor : "var(--line)";
        (e.currentTarget as HTMLElement).style.boxShadow = "var(--shadow-panel)";
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>
            port {p.port}
          </div>
          <div style={{
            fontSize: 14, fontWeight: 600, color: "var(--text)", marginTop: 2,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>
            {p.real_name}
          </div>
        </div>
        <span style={{
          flexShrink: 0,
          fontSize: 9,
          fontFamily: "var(--font-mono)",
          fontWeight: 500,
          textTransform: "uppercase",
          padding: "2px 7px",
          borderRadius: "var(--radius-pill)",
          background: statusBadgeColor(p.status),
          color: "#fff",
        }}>
          {p.status}
        </span>
      </div>

      <div style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: "4px 16px",
        marginTop: 12,
        fontSize: 11,
        color: "var(--muted)",
      }}>
        <div>Venue: <span style={{ color: "var(--text-2)" }}>{p.venue ?? "—"}</span></div>
        <div>Roles: <span style={{ color: "var(--text-2)" }}>{activeRoles}</span></div>
        <div>Branch: <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-2)" }}>{p.current_branch || "—"}</span></div>
        <div>Created: <span style={{ color: "var(--text-2)" }}>{new Date(p.created).toLocaleDateString()}</span></div>
      </div>
    </button>
  );
}
