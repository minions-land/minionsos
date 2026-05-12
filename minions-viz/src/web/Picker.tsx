import type { GruInfo } from "@shared/types";
import { selectGruProject } from "./store";

/** Initial Gru / Project picker shown when nothing is selected. */
export default function Picker({
  grus,
  selectedGruId,
}: {
  grus: GruInfo[];
  selectedGruId: string | null;
}) {
  const gru = grus.find((g) => g.id === selectedGruId) ?? null;

  if (!gru) {
    return (
      <div className="picker-grid">
        <div className="picker-card">
          <h1>Select a Gru</h1>
          <p className="sub">
            MinionsVIZ is a machine-wide Observatory. Each registered Gru is a
            MinionsOS installation on this host — pick one to inspect its
            projects.
          </p>
          {grus.length === 0 ? (
            <div className="empty">
              No Grus registered yet. Run <span className="mono">./viz register</span> in
              a MinionsOS checkout.
            </div>
          ) : (
            <div className="picker-list">
              {grus.map((g) => (
                <button
                  key={g.id}
                  className="picker-item"
                  onClick={() => selectGruProject(g.id, null)}
                >
                  <strong>{g.label}</strong>
                  <div className="meta">
                    <span
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        background: g.online ? "#22c55e" : "#ef4444",
                      }}
                    />
                    <span>{g.online ? "online" : "offline"}</span>
                    <span>·</span>
                    <span>{g.projects.length} project{g.projects.length === 1 ? "" : "s"}</span>
                  </div>
                  <div
                    className="meta"
                    style={{ marginTop: 4, color: "var(--muted-2)", fontSize: 9 }}
                  >
                    {g.rootPath}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="picker-grid">
      <div className="picker-card">
        <h1>Select a project</h1>
        <p className="sub">
          {gru.label} · {gru.projects.length} project
          {gru.projects.length === 1 ? "" : "s"}
        </p>
        {gru.projects.length === 0 ? (
          <div className="empty">No projects in this Gru. Create one via mos.</div>
        ) : (
          <div className="picker-list">
            {gru.projects.map((p) => (
              <button
                key={p.port}
                className="picker-item"
                onClick={() => selectGruProject(gru.id, p.port)}
              >
                <strong>{p.real_name}</strong>
                <div className="meta">
                  <span className="badge active" style={{
                    background: p.status === "active" ? "rgba(34,197,94,0.18)" : p.status === "dormant" ? "rgba(245,158,11,0.18)" : "rgba(100,116,139,0.18)",
                    color: p.status === "active" ? "#86efac" : p.status === "dormant" ? "#fcd34d" : "#94a3b8",
                  }}>{p.status}</span>
                  <span>port {p.port}</span>
                  <span>·</span>
                  <span>{p.active_roles?.length ?? 0} role
                    {(p.active_roles?.length ?? 0) === 1 ? "" : "s"}</span>
                </div>
              </button>
            ))}
          </div>
        )}
        <div style={{ marginTop: 16 }}>
          <button
            className="chip"
            onClick={() => selectGruProject(null, null)}
          >
            ← Change Gru
          </button>
        </div>
      </div>
    </div>
  );
}
