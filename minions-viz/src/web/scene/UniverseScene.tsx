import { useMemo, useRef } from "react";
import { Canvas, extend } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { XR } from "@react-three/xr";
import * as THREE from "three";
import type { AgentInfo, Message, MosProject } from "@shared/types";
import { roleBucket, ROLE_BUCKETS } from "../roleIdentity";
import { isGruAgent } from "../store";
import type { AgentActivity } from "../activity";
import OrbitLanes, { type Lane } from "./OrbitLanes";
import Nebula from "./Starfield";
import ProjectCore from "./ProjectCore";
import AgentSphere from "./AgentSphere";
import MessagePackets from "./MessagePackets";

extend(THREE as unknown as Record<string, unknown>);

interface Props {
  project: MosProject | null;
  agents: AgentInfo[];
  messages: Message[];
  activity: Map<string, AgentActivity>;
  selectedId: string | null;
  hoveredId: string | null;
  onSelectAgent: (a: AgentInfo | null) => void;
  onHoverAgent: (a: AgentInfo | null) => void;
}

interface Placement {
  agent: AgentInfo;
  radius: number;
  phase: number;
  tiltX: number;
  tiltZ: number;
  speed: number;
  laneIndex: number;
}

function layoutAgents(agents: AgentInfo[]): {
  placements: Placement[];
  lanes: Lane[];
  gru: AgentInfo | null;
} {
  const gru = agents.find((a) => isGruAgent(a.agent_id, a.name)) ?? null;
  const rest = agents.filter((a) => a !== gru);

  const groups = new Map<string, AgentInfo[]>();
  for (const a of rest) {
    const k = roleBucket(a.agent_id).key;
    const arr = groups.get(k) ?? [];
    arr.push(a);
    groups.set(k, arr);
  }
  for (const arr of groups.values()) {
    arr.sort((a, b) => a.agent_id.localeCompare(b.agent_id));
  }

  const orderedKeys = Array.from(groups.keys()).sort(
    (a, b) =>
      (ROLE_BUCKETS[a]?.orbitIndex ?? 99) -
      (ROLE_BUCKETS[b]?.orbitIndex ?? 99),
  );

  const placements: Placement[] = [];
  const lanes: Lane[] = [];
  const BASE_R = 3.6;
  const STEP = 1.8;

  orderedKeys.forEach((k, laneIdx) => {
    const bucket = ROLE_BUCKETS[k] ?? ROLE_BUCKETS.other;
    const instances = groups.get(k)!;
    const radius = BASE_R + laneIdx * STEP;
    const tiltX = ((laneIdx % 2 === 0 ? 1 : -1) * Math.PI) / 18;
    const tiltZ = ((laneIdx % 3) - 1) * 0.08;
    const laneSpeed = 0.18 / (1 + laneIdx * 0.18);
    lanes.push({ radius, color: bucket.color, tiltX, tiltZ, label: bucket.label });
    instances.forEach((agent, i) => {
      const phase = (i / Math.max(instances.length, 1)) * Math.PI * 2;
      placements.push({
        agent,
        radius,
        phase,
        tiltX,
        tiltZ,
        speed: laneSpeed,
        laneIndex: laneIdx,
      });
    });
  });

  return { placements, lanes, gru };
}

export { xrStore } from "./xrStore";

export default function UniverseScene({
  project,
  agents,
  messages,
  activity,
  selectedId,
  hoveredId,
  onSelectAgent,
  onHoverAgent,
}: Props) {
  const camRef = useRef<any>(null);
  const { placements, lanes, gru } = useMemo(
    () => layoutAgents(agents),
    [agents],
  );

  // Snapshot the static phase positions for message-packet endpoints.
  // (Live positions would require AgentSphere to publish them; using the
  // phase position is "good enough" since packets last ~2s.)
  const packetEndpoints = useMemo(() => {
    const m = new Map<string, { x: number; y: number; z: number }>();
    if (gru) m.set(gru.agent_id, { x: 0, y: 0, z: 0 });
    for (const p of placements) {
      const tiltMatrix = new THREE.Matrix4()
        .makeRotationX(p.tiltX)
        .multiply(new THREE.Matrix4().makeRotationZ(p.tiltZ));
      const v = new THREE.Vector3(
        Math.cos(p.phase) * p.radius,
        0,
        Math.sin(p.phase) * p.radius,
      );
      v.applyMatrix4(tiltMatrix);
      m.set(p.agent.agent_id, { x: v.x, y: v.y, z: v.z });
    }
    return m;
  }, [placements, gru]);

  return (
    <Canvas
      camera={{ position: [0, 7, 16], fov: 50, near: 0.1, far: 500 }}
      onCreated={(s) => {
        s.gl.setClearColor("#04060c", 1);
      }}
      onPointerMissed={() => onSelectAgent(null)}
      dpr={[1, 1.25]}
      gl={{ antialias: false, alpha: false, powerPreference: "high-performance" }}
    >
      <XR>
        <color attach="background" args={["#04060c"]} />
        <fog attach="fog" args={["#04060c", 38, 105]} />

        <ambientLight intensity={0.3} />
        <pointLight
          position={[0, 0, 0]}
          intensity={3.2}
          distance={55}
          color="#F59E0B"
          decay={1.2}
        />
        <pointLight position={[18, 12, 12]} intensity={0.55} color="#60a5fa" />
        <pointLight position={[-14, -8, -10]} intensity={0.35} color="#c084fc" />
        <pointLight position={[5, -10, 15]} intensity={0.25} color="#f0abfc" />

        <Nebula />
        <OrbitLanes lanes={lanes} />

        <ProjectCore
          projectName={project?.real_name ?? "No Project"}
          active={gru != null}
        />

        {placements.map((p) => {
          const act = activity.get(p.agent.agent_id) ?? { state: "idle" as const, pending: 0, executing: 0, busyOn: null };
          return (
            <AgentSphere
              key={p.agent.agent_id}
              agent={p.agent}
              radius={p.radius}
              phase={p.phase}
              tiltX={p.tiltX}
              tiltZ={p.tiltZ}
              speed={p.speed}
              state={act.state}
              pendingEvents={act.pending}
              selected={selectedId === p.agent.agent_id}
              hovered={hoveredId === p.agent.agent_id}
              onSelect={(a) => onSelectAgent(a)}
              onHover={(a) => onHoverAgent(a)}
            />
          );
        })}

        <MessagePackets messages={messages} placements={packetEndpoints} />

        <OrbitControls
          ref={camRef}
          enableDamping
          dampingFactor={0.08}
          minDistance={4}
          maxDistance={55}
          makeDefault
        />
      </XR>
    </Canvas>
  );
}
