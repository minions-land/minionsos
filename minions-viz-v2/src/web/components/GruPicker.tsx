import { selectGru } from "../hooks/useStore";
import type { GruInfo } from "@shared/types";
import { Crown } from "@phosphor-icons/react";

interface Props {
  grus: GruInfo[];
}

function freshness(lastSeen: string | null): { label: string; isLive: boolean } {
  if (!lastSeen) return { label: "never", isLive: false };
  const age = Date.now() - new Date(lastSeen).getTime();
  if (age <= 30_000) return { label: "live", isLive: true };
  if (age <= 120_000) return { label: "recent", isLive: false };
  return { label: "stale", isLive: false };
}

export default function GruPicker({ grus }: Props) {
  const sorted = [...grus].sort((a, b) => {
    const order = (g: GruInfo) => {
      const f = freshness(g.lastSeen);
      if (f.label === "live") return 0;
      if (f.label === "recent") return 1;
      return 2;
    };
    return order(a) - order(b);
  });

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
        <div style={{ marginBottom: 32 }}>
          <div className="section-label" style={{ marginBottom: 4 }}>MinionsOS</div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: "var(--text)", margin: 0 }}>
            Gru Installations
          </h1>
          <p style={{ fontSize: 12, color: "var(--muted)", marginTop: 6 }}>
            Each Gru is one MinionsOS checkout on this host. Pick one to view its projects.
          </p>
        </div>

        {grus.length === 0 && (
          <div className="surface-card" style={{ padding: 40, textAlign: "center" }}>
            <div className="empty-state">
              <Crown size={40} weight="thin" style={{ color: "var(--muted)", opacity: 0.4 }} />
              <p style={{ color: "var(--muted)" }}>
                No Grus registered yet. Run <code style={{
                  fontFamily: "var(--font-mono)", fontSize: 11,
                  background: "var(--surface)", padding: "2px 6px", borderRadius: 4,
                }}>./gru</code> in any MinionsOS checkout.
              </p>
            </div>
          </div>
        )}

        {/* Cards grid */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))",
          gap: 16,
        }}>
          {sorted.map((g, idx) => {
            const f = freshness(g.lastSeen);
            const active = g.projects.filter((p) => p.status === "active").length;
            const dormant = g.projects.filter((p) => p.status === "dormant").length;
            const closed = g.projects.filter((p) => p.status === "closed").length;

            return (
              <button
                key={g.id}
                onClick={() => selectGru(g.id)}
                className="animate-fade-in"
                style={{
                  animationDelay: `${idx * 80}ms`,
                  animationFillMode: "both",
                  textAlign: "left",
                  padding: 20,
                  borderRadius: "var(--radius-sm)",
                  border: `1px solid ${f.isLive ? "var(--role-gru)" : "var(--line)"}`,
                  background: "var(--panel-bg)",
                  backdropFilter: "blur(16px)",
                  WebkitBackdropFilter: "blur(16px)",
                  boxShadow: f.isLive ? "0 0 20px rgba(245,158,11,0.15)" : "var(--shadow-panel)",
                  opacity: f.isLive ? 1 : 0.6,
                  cursor: "pointer",
                  transition: `opacity 200ms var(--ease-out), border-color 200ms var(--ease-out), box-shadow 200ms var(--ease-out)`,
                }}
                onMouseEnter={(e) => {
                  if (!f.isLive) (e.currentTarget as HTMLElement).style.opacity = "0.85";
                }}
                onMouseLeave={(e) => {
                  if (!f.isLive) (e.currentTarget as HTMLElement).style.opacity = "0.6";
                }}
              >
                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>
                      gru · {g.id}
                    </div>
                    <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text)", marginTop: 3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {g.label}
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
                    {f.isLive && (
                      <span style={{
                        fontSize: 9, fontWeight: 700, letterSpacing: "0.08em",
                        padding: "2px 6px", borderRadius: "var(--radius-pill)",
                        background: "var(--role-gru)", color: "#000",
                      }}>
                        LIVE
                      </span>
                    )}
                    <span style={{
                      display: "inline-flex", alignItems: "center", gap: 5,
                      fontSize: 10, fontFamily: "var(--font-mono)",
                      padding: "3px 8px", borderRadius: "var(--radius-pill)",
                      border: "1px solid var(--line)", background: "var(--surface)",
                      color: "var(--muted)",
                    }}>
                      <span style={{
                        width: 6, height: 6, borderRadius: "50%",
                        background: f.isLive ? "#10B981" : f.label === "recent" ? "#F59E0B" : "#EF4444",
                      }} />
                      {f.label}
                    </span>
                  </div>
                </div>

                <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted-2)", marginTop: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {g.rootPath}
                </div>

                <div style={{
                  display: "grid", gridTemplateColumns: "1fr 1fr 1fr",
                  gap: 8, marginTop: 14, fontSize: 11, color: "var(--muted)",
                }}>
                  <div>Active: <span style={{ color: "var(--text)", fontWeight: 600 }}>{active}</span></div>
                  <div>Dormant: <span style={{ color: "var(--text)", fontWeight: 600 }}>{dormant}</span></div>
                  <div>Closed: <span style={{ color: "var(--text)", fontWeight: 600 }}>{closed}</span></div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
