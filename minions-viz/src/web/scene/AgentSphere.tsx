import { useRef, useMemo } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import type { AgentInfo } from "@shared/types";
import { roleBucket, agentShortTag } from "../roleIdentity";

interface Props {
  agent: AgentInfo;
  /** Orbit parameters — circular in lane's tilted plane. */
  radius: number;
  phase: number;
  tiltX: number;
  tiltZ: number;
  speed: number;
  state: "active" | "idle";
  pendingEvents: number;
  selected: boolean;
  hovered: boolean;
  onSelect: (agent: AgentInfo) => void;
  onHover: (agent: AgentInfo | null) => void;
}

/**
 * One entity per AgentCard — never deduplicated by role. Geometry differs
 * per role bucket so spheres aren't the only distinguisher:
 *
 *   - Coder       → icosahedron (faceted crystal)
 *   - Noter       → octahedron (diamond)
 *   - Writer      → tetrahedron (pen-tip cone)
 *   - Reviewer    → low-res sphere (lens)
 *   - Expert      → dodecahedron (dense crystal)
 *   - Ethics      → cylinder (pillar)
 *   - Other       → sphere
 *
 * Active agents orbit; idle agents sit still at their phase position and
 * dim. A pending-event ring only appears when pendingEvents > 0.
 */
function RoleGeometry({
  kind,
  size,
}: {
  kind: string;
  size: number;
}) {
  switch (kind) {
    case "coder":
      return <icosahedronGeometry args={[size, 0]} />;
    case "noter":
      return <octahedronGeometry args={[size, 0]} />;
    case "writer":
      return <tetrahedronGeometry args={[size * 1.15, 0]} />;
    case "reviewer":
      return <sphereGeometry args={[size, 8, 6]} />;
    case "expert":
      return <dodecahedronGeometry args={[size, 0]} />;
    case "ethics":
      return <cylinderGeometry args={[size * 0.7, size * 0.7, size * 1.9, 6]} />;
    default:
      return <sphereGeometry args={[size, 16, 12]} />;
  }
}

export default function AgentSphere({
  agent,
  radius,
  phase,
  tiltX,
  tiltZ,
  speed,
  state,
  pendingEvents,
  selected,
  hovered,
  onSelect,
  onHover,
}: Props) {
  const groupRef = useRef<THREE.Group>(null);
  const meshRef = useRef<THREE.Mesh>(null);
  const ringRef = useRef<THREE.Mesh>(null);
  const orbitPosRef = useRef(new THREE.Vector3());
  const tiltMatrix = useMemo(() => {
    // Rotation that tilts the (x,z) orbit plane by tiltX around x and tiltZ around z
    return new THREE.Matrix4()
      .makeRotationX(tiltX)
      .multiply(new THREE.Matrix4().makeRotationZ(tiltZ));
  }, [tiltX, tiltZ]);

  const bucket = useMemo(() => roleBucket(agent.agent_id), [agent.agent_id]);
  const color = bucket.color;
  const baseSize = 0.24 + Math.min(agent.reputation ?? 0.5, 1) * 0.18;

  // Per-agent angle tracker. Roles always advance — Noter and Ethics may not
  // register EACN traffic but they are long-lived processes, not asleep.
  // "Active" only modulates speed and pulse, not whether the orbit moves.
  const angleRef = useRef(phase);

  useFrame((state3, delta) => {
    const gRef = groupRef.current;
    if (!gRef) return;
    const t = state3.clock.elapsedTime;

    // Always orbit. Active roles glide ~3× faster than idle baseline.
    const baseSpeed = speed * 0.35;
    const activeSpeed = speed;
    angleRef.current += (state === "active" ? activeSpeed : baseSpeed) * delta;
    const a = angleRef.current;
    orbitPosRef.current
      .set(Math.cos(a) * radius, 0, Math.sin(a) * radius)
      .applyMatrix4(tiltMatrix);
    gRef.position.copy(orbitPosRef.current);

    // Rotate on local axis for visual life; active spins faster.
    if (meshRef.current) {
      meshRef.current.rotation.x += delta * (state === "active" ? 0.8 : 0.2);
      meshRef.current.rotation.y += delta * (state === "active" ? 1.1 : 0.3);
    }

    // Pending ring rotation speed scales with pending count.
    if (ringRef.current) {
      const visible = pendingEvents > 0;
      ringRef.current.visible = visible;
      if (visible) {
        ringRef.current.rotation.z +=
          delta * (0.8 + Math.min(pendingEvents, 20) * 0.15);
      }
    }

    // Subtle pulse for idle, stronger for active.
    const pulse =
      state === "active"
        ? 1 + Math.sin(t * 2.6) * 0.06
        : 1 + Math.sin(t * 1.2) * 0.025;
    const scl = pulse * (selected || hovered ? 1.25 : 1);
    if (meshRef.current) meshRef.current.scale.setScalar(scl);
  });

  // Idle roles dim slightly but stay visible — they're alive, just quiet.
  const dim = state === "idle" ? 0.72 : 1;
  const ringColor = pendingEvents > 20
    ? "#ef4444"
    : pendingEvents > 10
      ? "#f59e0b"
      : pendingEvents > 3
        ? "#fbbf24"
        : color;

  return (
    <group ref={groupRef}>
      <mesh
        ref={meshRef}
        onClick={(e) => {
          e.stopPropagation();
          onSelect(agent);
        }}
        onPointerOver={(e) => {
          e.stopPropagation();
          onHover(agent);
        }}
        onPointerOut={() => onHover(null)}
      >
        <RoleGeometry kind={bucket.key} size={baseSize} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={(selected ? 2.4 : 1.35) * dim}
          roughness={0.42}
          metalness={0.2}
          flatShading
        />
      </mesh>

      {/* Outer glow */}
      <mesh>
        <sphereGeometry args={[baseSize * 1.7, 10, 8]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={0.12 * dim}
          depthWrite={false}
        />
      </mesh>

      {/* Pending-event ring — only shows when events are queued. */}
      <mesh ref={ringRef} rotation={[Math.PI / 2.4, 0, 0]}>
        <ringGeometry args={[baseSize * 1.55, baseSize * 1.78, 28]} />
        <meshBasicMaterial
          color={ringColor}
          transparent
          opacity={0.72}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>

      {/* Selection ring (static) */}
      {selected && (
        <mesh rotation={[Math.PI / 2.4, 0, 0]}>
          <ringGeometry args={[baseSize * 2.05, baseSize * 2.22, 36]} />
          <meshBasicMaterial
            color="#ffffff"
            transparent
            opacity={0.85}
            side={THREE.DoubleSide}
            depthWrite={false}
          />
        </mesh>
      )}

      {(hovered || selected) && (
        <Html position={[0, baseSize * 2.6, 0]} center distanceFactor={10}>
          <div
            style={{
              padding: "3px 9px",
              fontFamily: "var(--font-mono)",
              fontSize: 11,
              background: "rgba(8,11,20,0.88)",
              border: `1px solid ${color}66`,
              borderRadius: 4,
              color: "#f1f5f9",
              whiteSpace: "nowrap",
              pointerEvents: "none",
            }}
          >
            <span style={{ color }}>{agentShortTag(agent.agent_id)}</span>{" "}
            <span style={{ color: "#cbd5e1" }}>
              {agent.name || agent.agent_id}
            </span>
            {pendingEvents > 0 && (
              <span
                style={{
                  marginLeft: 6,
                  color: "#fbbf24",
                  fontSize: 10,
                }}
              >
                ● {pendingEvents} pending
              </span>
            )}
          </div>
        </Html>
      )}
    </group>
  );
}
