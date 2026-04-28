import { useState, useRef, useEffect, useCallback } from "react";
import { WifiSlash, Robot } from "@phosphor-icons/react";
import { useStore, gruById, projectByPort } from "../../hooks/useStore";
import { useAnimationFrame } from "../../hooks/useAnimationFrame";
import { useOrbitalEngine } from "./useOrbitalEngine";
import { SolarSystemCanvas } from "./SolarSystemCanvas";
import { StarNode } from "./StarNode";
import { PlanetNode } from "./PlanetNode";
import EmptyState from "../../components/EmptyState";

interface Props {
  onSelectAgent: (id: string) => void;
}

export default function SolarSystemPage({ onSelectAgent }: Props) {
  const store = useStore();
  const gru = gruById(store.grus, store.selectedGruId);
  const project = gru ? projectByPort(gru.projects, store.selectedPort) : null;
  const projectName = project?.real_name ?? "Project";

  const engine = useOrbitalEngine();
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });

  // Track container size via ResizeObserver
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setSize({ w: Math.round(width), h: Math.round(height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Resize engine when container changes
  useEffect(() => {
    if (size.w > 0 && size.h > 0) engine.resize(size.w, size.h);
  }, [size.w, size.h, engine.resize]);

  // Sync agents into orbital engine
  useEffect(() => {
    const gruAgent = store.agents.find(
      (a) =>
        a.agent_id.toLowerCase().includes("gru") ||
        a.name.toLowerCase().includes("gru"),
    );
    const roleAgents = store.agents.filter(
      (a) =>
        !a.agent_id.toLowerCase().includes("gru") &&
        !a.name.toLowerCase().includes("gru"),
    );
    engine.syncAgents(roleAgents, gruAgent);
  }, [store.agents, engine.syncAgents]);

  // Force re-render each frame so HTML nodes track stateRef positions
  const [, setFrame] = useState(0);
  useAnimationFrame(() => setFrame((f) => f + 1));

  // Hover detection via mouse proximity to planets
  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const s = engine.stateRef.current;
      let hoveredKey: string | null = null;
      for (const p of s.planets) {
        const dx = mx - p.x;
        const dy = my - p.y;
        const hitR = 30 * p.scale;
        if (dx * dx + dy * dy < hitR * hitR) {
          hoveredKey = p.key;
          break;
        }
      }
      engine.setHovered(hoveredKey);
    },
    [engine],
  );

  const handleMouseLeave = useCallback(() => {
    engine.setHovered(null);
  }, [engine]);

  // Not connected
  if (!store.connected) {
    return (
      <div
        ref={containerRef}
        style={{
          position: "relative",
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <EmptyState icon={WifiSlash} message="Waiting for connection..." />
      </div>
    );
  }

  // No agents registered
  if (store.agents.length === 0) {
    return (
      <div
        ref={containerRef}
        style={{
          position: "relative",
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <EmptyState icon={Robot} message="No agents registered yet" />
      </div>
    );
  }

  const s = engine.stateRef.current;

  return (
    <div
      ref={containerRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        overflow: "hidden",
      }}
    >
      {/* Canvas: orbits, glows, beams, particles */}
      <SolarSystemCanvas
        stateRef={engine.stateRef}
        tick={engine.tick}
        width={size.w}
        height={size.h}
      />

      {/* HTML overlay: interactive nodes */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: size.w,
          height: size.h,
          pointerEvents: "none",
        }}
      >
        <StarNode
          x={s.star.x}
          y={s.star.y}
          projectName={projectName}
          active={s.star.active}
        />

        {s.planets.map((p) => (
          <PlanetNode
            key={p.key}
            roleKey={p.key}
            x={p.x}
            y={p.y}
            scale={p.scale}
            opacity={p.opacity}
            state={p.state}
            hovered={p.hovered}
            bufferCount={p.bufferCount}
            nodeAlpha={p.nodeAlpha}
            onClick={() => onSelectAgent(p.key)}
            onMouseEnter={() => engine.setHovered(p.key)}
            onMouseLeave={() => engine.setHovered(null)}
          />
        ))}
      </div>
    </div>
  );
}
