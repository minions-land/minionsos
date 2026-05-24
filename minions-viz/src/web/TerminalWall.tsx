import { useEffect, useMemo, useRef, useState } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import type { AgentInfo } from "@shared/types";
import { roleBucket, ROLE_BUCKETS, agentShortTag } from "./roleIdentity";
import { subscribeRoleLog, unsubscribeRoleLog, useRoleLog } from "./store";

/**
 * Terminal grid, grouped by role bucket: each role bucket occupies one row,
 * with its instances laid out as equal-size panes.
 *
 * Each pane mounts a real xterm.js emulator instead of a plain `<div>`. This
 * mirrors the MinionsCode macOS app's SwiftTerm-based terminal — ANSI colors
 * render, cursor positioning works, line wrapping respects the pane width,
 * and the pane looks like a real terminal instead of a partially-stripped
 * text dump.
 */
interface Props {
  agents: AgentInfo[];
}

export default function TerminalWall({ agents }: Props) {
  const rows = useMemo(() => {
    const m = new Map<string, AgentInfo[]>();
    for (const a of agents) {
      const k = roleBucket(a.agent_id).key;
      const arr = m.get(k) ?? [];
      arr.push(a);
      m.set(k, arr);
    }
    const keys = Array.from(m.keys()).sort(
      (a, b) =>
        (ROLE_BUCKETS[a]?.orbitIndex ?? 99) -
        (ROLE_BUCKETS[b]?.orbitIndex ?? 99),
    );
    return keys.map((k) => ({
      key: k,
      bucket: ROLE_BUCKETS[k] ?? ROLE_BUCKETS.other,
      items: m.get(k)!.sort((a, b) => a.agent_id.localeCompare(b.agent_id)),
    }));
  }, [agents]);

  if (agents.length === 0) {
    return (
      <div className="terminal-wall empty-wall">
        <div className="empty">No agent instances registered yet.</div>
      </div>
    );
  }

  return (
    <div className="terminal-wall">
      {rows.map((row) => (
        <div key={row.key} className="term-row">
          <div className="term-row-label" style={{ color: row.bucket.color }}>
            <span className="tint" style={{ background: row.bucket.color }} />
            {row.bucket.label}
            <span style={{ color: "var(--muted)", marginLeft: 8 }}>× {row.items.length}</span>
          </div>
          <div
            className="term-row-grid"
            style={{
              gridTemplateColumns: `repeat(${Math.min(row.items.length, 4)}, minmax(0, 1fr))`,
            }}
          >
            {row.items.map((a) => (
              <TerminalPane key={a.agent_id} agent={a} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function TerminalPane({ agent }: { agent: AgentInfo }) {
  const bucket = useMemo(() => roleBucket(agent.agent_id), [agent.agent_id]);
  const role = bucket.key;
  const [paused, setPaused] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const writtenRef = useRef<number>(0);
  const buffer = useRoleLog(role);

  // Subscribe to the role's log stream once per pane.
  useEffect(() => {
    subscribeRoleLog(role);
    return () => {
      unsubscribeRoleLog(role);
    };
  }, [role]);

  // Mount the xterm.js terminal once, on first render.
  useEffect(() => {
    if (!containerRef.current) return;
    const term = new Terminal({
      fontFamily:
        'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco, "Liberation Mono", "Courier New", monospace',
      fontSize: 11,
      lineHeight: 1.25,
      cursorBlink: false,
      cursorStyle: "block",
      scrollback: 5000,
      convertEol: true, // MinionsOS log streams have plain '\n', no '\r\n'
      disableStdin: true, // read-only observatory; do not capture keys
      theme: {
        background: "#0a0d12",
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
      // first fit can throw if the container is 0x0; the resize observer
      // below will retry on the next layout pass.
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

  // Stream the role log into the terminal incrementally, avoiding repeated
  // full rewrites that would clear the screen on every batch.
  useEffect(() => {
    const term = termRef.current;
    if (!term || paused) return;
    const written = writtenRef.current;
    if (buffer.length < written) {
      // Buffer was reset (e.g. role restarted) — wipe and rewrite.
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

  return (
    <div className="term-pane">
      <header>
        <span className="swatch" style={{ background: bucket.color, color: bucket.color }} />
        <span className="title">
          <span style={{ color: bucket.color }}>{bucket.label}</span>
          <span style={{ color: "var(--muted)" }}> · {agent.name || agent.agent_id}</span>
        </span>
        <span className="meta">{agentShortTag(agent.agent_id)}</span>
        <span className="meta">{lineCount} ln</span>
        <button
          className="chip"
          style={{ height: 22, padding: "0 10px", fontSize: 10 }}
          onClick={() => setPaused((p) => !p)}
          aria-pressed={paused}
        >
          {paused ? "follow" : "pause"}
        </button>
      </header>
      <div className="term-body" ref={containerRef} />
    </div>
  );
}
