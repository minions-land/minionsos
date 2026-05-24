import { useEffect, useMemo, useRef, useState } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import type { AgentInfo } from "@shared/types";
import { roleBucket, ROLE_BUCKETS, agentShortTag } from "./roleIdentity";
import { isGruAgent, subscribeRoleLog, unsubscribeRoleLog, useRoleLog } from "./store";

/**
 * Terminal grid styled after Minions Code (SwiftTerm).
 *
 * Layout rules (per-row, not global — single-instance rows shouldn't be
 * forced narrow just because some other row has 4 instances):
 *
 *   - 1 instance  → row spans full width (1 column)
 *   - 2 instances → 2 equal columns
 *   - 3+ instances → 3 columns; instance #4+ wraps to a new row
 *
 * Gru is special-cased: it isn't a tmux-hosted Role and isn't on EACN, so it
 * never appears in `agents`. We always synthesise a Gru row at the top that
 * tails `<gruRoot>/minions/state/logs/gru.log` via the `gru` virtual role.
 */
interface Props {
  agents: AgentInfo[];
}

const MAX_COLS_PER_ROW = 3;

interface RoleRow {
  key: string;
  bucket: typeof ROLE_BUCKETS[string];
  // null indicates a virtual pane (Gru — no AgentCard registered on EACN).
  items: Array<AgentInfo | null>;
}

export default function TerminalWall({ agents }: Props) {
  const rows: RoleRow[] = useMemo(() => {
    const m = new Map<string, AgentInfo[]>();
    for (const a of agents) {
      // Skip an EACN-registered Gru agent (rare) — we render Gru ourselves
      // from the gru.log file. Otherwise the same role would appear twice.
      if (isGruAgent(a.agent_id, a.name)) continue;
      const k = roleBucket(a.agent_id).key;
      const arr = m.get(k) ?? [];
      arr.push(a);
      m.set(k, arr);
    }
    const orderedKeys = Array.from(m.keys()).sort(
      (a, b) =>
        (ROLE_BUCKETS[a]?.orbitIndex ?? 99) -
        (ROLE_BUCKETS[b]?.orbitIndex ?? 99),
    );

    const out: RoleRow[] = [];
    // Always lead with the Gru row, regardless of agents[].
    out.push({
      key: "gru",
      bucket: ROLE_BUCKETS.gru,
      items: [null],
    });
    for (const k of orderedKeys) {
      out.push({
        key: k,
        bucket: ROLE_BUCKETS[k] ?? ROLE_BUCKETS.other,
        items: m
          .get(k)!
          .sort((a, b) => a.agent_id.localeCompare(b.agent_id)),
      });
    }
    return out;
  }, [agents]);

  return (
    <div className="terminal-wall">
      {rows.map((row) => {
        const cols = Math.min(MAX_COLS_PER_ROW, Math.max(1, row.items.length));
        return (
          <div key={row.key} className="term-row">
            <div className="term-row-label" style={{ color: row.bucket.color }}>
              <span className="tint" style={{ background: row.bucket.color }} />
              {row.bucket.label}
              <span style={{ color: "var(--muted)", marginLeft: 8 }}>
                × {row.items.length}
              </span>
            </div>
            <div
              className="term-row-grid"
              style={{
                gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
              }}
            >
              {row.items.map((a, i) => (
                <TerminalPane
                  key={a ? a.agent_id : `${row.key}-virtual-${i}`}
                  role={row.key}
                  agent={a}
                />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function TerminalPane({
  role,
  agent,
}: {
  role: string;
  agent: AgentInfo | null;
}) {
  const bucket = useMemo(
    () => ROLE_BUCKETS[role] ?? ROLE_BUCKETS.other,
    [role],
  );
  const [paused, setPaused] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const writtenRef = useRef<number>(0);
  const buffer = useRoleLog(role);

  useEffect(() => {
    subscribeRoleLog(role);
    return () => {
      unsubscribeRoleLog(role);
    };
  }, [role]);

  useEffect(() => {
    if (!containerRef.current) return;
    const term = new Terminal({
      fontFamily:
        'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco, "JetBrains Mono", "Liberation Mono", "Courier New", monospace',
      fontSize: 12,
      lineHeight: 1.3,
      letterSpacing: 0,
      cursorBlink: false,
      cursorStyle: "block",
      scrollback: 5000,
      convertEol: true,
      disableStdin: true,
      allowTransparency: false,
      theme: {
        background: "#0b0e15",
        foreground: "#d4d8e0",
        cursor: "#7a8aa8",
        selectionBackground: "rgba(125,146,180,0.35)",
        black: "#1a1f29",
        red: "#f87171",
        green: "#4ade80",
        yellow: "#fbbf24",
        blue: "#60a5fa",
        magenta: "#c084fc",
        cyan: "#22d3ee",
        white: "#cbd5e1",
        brightBlack: "#475569",
        brightRed: "#fca5a5",
        brightGreen: "#86efac",
        brightYellow: "#fcd34d",
        brightBlue: "#93c5fd",
        brightMagenta: "#d8b4fe",
        brightCyan: "#67e8f9",
        brightWhite: "#f1f5f9",
      },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(containerRef.current);
    try {
      fit.fit();
    } catch {
      // first fit can throw if the container is 0x0; resize observer retries
    }
    termRef.current = term;
    fitRef.current = fit;

    const ro = new ResizeObserver(() => {
      try {
        fit.fit();
      } catch {
        // ignore intermediate resize hiccups
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      term.dispose();
      termRef.current = null;
      fitRef.current = null;
      writtenRef.current = 0;
    };
  }, []);

  useEffect(() => {
    const term = termRef.current;
    if (!term || paused) return;
    const written = writtenRef.current;
    if (buffer.length < written) {
      term.reset();
      term.write(buffer);
      writtenRef.current = buffer.length;
      return;
    }
    if (buffer.length > written) {
      term.write(buffer.slice(written));
      writtenRef.current = buffer.length;
    }
  }, [buffer, paused]);

  const lineCount = useMemo(
    () => (buffer.match(/\n/g)?.length ?? 0) + (buffer.length > 0 ? 1 : 0),
    [buffer],
  );

  // Pane title:
  //   real agent  → "<RoleLabel> · <agent name or id>"
  //   virtual gru → "Gru · gru.log"
  const title = agent
    ? agent.name || agent.agent_id
    : role === "gru"
      ? "gru.log"
      : bucket.label;
  const tag = agent ? agentShortTag(agent.agent_id) : role.toUpperCase();

  return (
    <div
      className="term-pane"
      style={{ ["--pane-color" as string]: bucket.color }}
    >
      <header>
        <div className="term-traffic">
          <span className="dot dot-r" />
          <span className="dot dot-y" />
          <span className="dot dot-g" />
        </div>
        <span className="title">
          <span style={{ color: bucket.color, fontWeight: 600 }}>
            {bucket.label}
          </span>
          <span style={{ color: "var(--muted)" }}> · {title}</span>
        </span>
        <span className="meta">{tag}</span>
        <span className="meta">{lineCount} ln</span>
        <button
          className="term-action"
          onClick={() => setPaused((p) => !p)}
          aria-pressed={paused}
          title={paused ? "Resume tail" : "Pause tail"}
        >
          {paused ? "▶" : "❚❚"}
        </button>
      </header>
      <div className="term-body" ref={containerRef} />
    </div>
  );
}
