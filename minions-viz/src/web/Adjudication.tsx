import { useMemo } from "react";
import type { AgentInfo, Task } from "@shared/types";
import { roleBucket, agentShortTag } from "./roleIdentity";

/**
 * Adjudication view — filters tasks of type "adjudication" and renders each
 * as a panel showing the adjudicators and per-result verdicts/scores.
 */
interface Props {
  tasks: Task[];
  agents: AgentInfo[];
}

export default function Adjudication({ tasks, agents }: Props) {
  const adj = useMemo(
    () => tasks.filter((t) => t.type === "adjudication"),
    [tasks],
  );

  const nameFor = (id: string) =>
    agents.find((a) => a.agent_id === id)?.name || id;

  if (adj.length === 0) {
    return (
      <div className="adj-empty">
        <div className="empty">No adjudication tasks yet.</div>
      </div>
    );
  }

  return (
    <div className="adj-wall">
      {adj.map((t) => {
        const initiator = roleBucket(t.initiator_id);
        return (
          <div key={t.id} className="adj-card">
            <header style={{ borderBottomColor: initiator.color + "55" }}>
              <span className="swatch" style={{ background: initiator.color }} />
              <span className="title">
                <span style={{ color: initiator.color }}>adjudication</span>
                <span style={{ color: "var(--muted)", marginLeft: 8 }}>#{t.id.slice(0, 10)}</span>
              </span>
              <span className={`badge ${t.status === "completed" ? "active" : "sleeping"}`}>{t.status}</span>
            </header>
            <div className="adj-body">
              <p className="adj-desc">
                {(() => {
                  const c = t.content as Record<string, unknown>;
                  if (typeof c?.description === "string") return c.description;
                  if (typeof c?.content === "string") return c.content as string;
                  return JSON.stringify(t.content);
                })()}
              </p>
              <div className="adj-grid">
                <div>
                  <div className="adj-sub">Initiator</div>
                  <div className="adj-val" style={{ color: initiator.color }}>
                    {agentShortTag(t.initiator_id)} · {nameFor(t.initiator_id)}
                  </div>
                </div>
                <div>
                  <div className="adj-sub">Domains</div>
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                    {t.domains.map((d) => (
                      <span key={d} className="tag">{d}</span>
                    ))}
                  </div>
                </div>
                {t.deadline && (
                  <div>
                    <div className="adj-sub">Deadline</div>
                    <div className="adj-val">{t.deadline}</div>
                  </div>
                )}
                {t.max_depth !== undefined && (
                  <div>
                    <div className="adj-sub">Depth</div>
                    <div className="adj-val">{t.depth} / {t.max_depth}</div>
                  </div>
                )}
              </div>

              {t.results?.length > 0 && (
                <>
                  <div className="adj-section">Results</div>
                  <div className="adj-results">
                    {t.results.map((r, i) => {
                      const bucket = roleBucket(r.agent_id);
                      return (
                        <div key={i} className="adj-result">
                          <div
                            className="adj-result-head"
                            style={{ borderLeftColor: bucket.color }}
                          >
                            <span style={{ color: bucket.color }}>
                              {agentShortTag(r.agent_id)}
                            </span>
                            <span style={{ color: "var(--muted)" }}>
                              {nameFor(r.agent_id)}
                            </span>
                            {r.selected && (
                              <span className="badge active" style={{ marginLeft: "auto" }}>selected</span>
                            )}
                          </div>
                          {r.adjudications?.length > 0 && (
                            <ul className="adj-verdicts">
                              {r.adjudications.map((a, j) => (
                                <li key={j}>
                                  <span style={{ color: "var(--muted)" }}>
                                    {agentShortTag(a.adjudicator_id)}
                                  </span>
                                  <span style={{ margin: "0 6px", color: "var(--muted)" }}>·</span>
                                  <span>{a.verdict}</span>
                                  <span
                                    className="tag"
                                    style={{
                                      marginLeft: 8,
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
                  </div>
                </>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
