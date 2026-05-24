import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import type { AgentInfo, Message } from "@shared/types";
import { roleBucket } from "../roleIdentity";

/**
 * Visual message packets — small glowing comets that travel from the sender's
 * orbital position to the receiver's, then fade out.
 *
 * Without this, the universe view looks frozen even when the network is
 * actively chatty. Messages already flow through the store; we just need a
 * visible cue. We don't try to reproduce the message content — the EventLog
 * tab covers that. This is purely a "is the network alive?" signal.
 */
const PACKET_LIFETIME_MS = 2200;
const MAX_PACKETS = 60;
const RECENT_WINDOW_MS = 12_000;

interface Props {
  messages: Message[];
  placements: Map<string, { x: number; y: number; z: number }>;
}

interface Packet {
  id: string;
  from: THREE.Vector3;
  to: THREE.Vector3;
  startedAt: number;
  color: THREE.Color;
}

export default function MessagePackets({ messages, placements }: Props) {
  const groupRef = useRef<THREE.Group>(null);
  const packetsRef = useRef<Packet[]>([]);
  const seenIdsRef = useRef<Set<string>>(new Set());

  // Ingest new messages → packets. Only animate messages we haven't seen yet
  // AND that arrived in the recent window (so a page refresh doesn't fire 200
  // packets for stale traffic).
  useEffect(() => {
    const now = Date.now();
    let added = 0;
    for (const m of messages) {
      if (seenIdsRef.current.has(m.id)) continue;
      seenIdsRef.current.add(m.id);
      const ts = Date.parse(m.timestamp);
      if (!Number.isFinite(ts) || now - ts > RECENT_WINDOW_MS) continue;
      const from = placements.get(m.from_agent_id);
      const to = placements.get(m.to_agent_id);
      if (!from || !to) continue;
      const bucket = roleBucket(m.from_agent_id);
      packetsRef.current.push({
        id: m.id,
        from: new THREE.Vector3(from.x, from.y, from.z),
        to: new THREE.Vector3(to.x, to.y, to.z),
        startedAt: now,
        color: new THREE.Color(bucket.color),
      });
      added += 1;
    }
    if (added && packetsRef.current.length > MAX_PACKETS) {
      packetsRef.current.splice(0, packetsRef.current.length - MAX_PACKETS);
    }
    // Cap the seen-ids set so it doesn't grow unbounded.
    if (seenIdsRef.current.size > 5000) {
      const recent = new Set<string>();
      for (const m of messages) recent.add(m.id);
      seenIdsRef.current = recent;
    }
  }, [messages, placements]);

  // Refs to the sphere instances, allocated up-front.
  const meshes = useMemo(
    () =>
      Array.from({ length: MAX_PACKETS }, () => ({
        mesh: null as THREE.Mesh | null,
        trail: null as THREE.Mesh | null,
      })),
    [],
  );

  useFrame(() => {
    const now = Date.now();
    // Drop expired packets.
    packetsRef.current = packetsRef.current.filter(
      (p) => now - p.startedAt < PACKET_LIFETIME_MS,
    );

    for (let i = 0; i < MAX_PACKETS; i++) {
      const slot = meshes[i];
      const packet = packetsRef.current[i];
      if (!slot.mesh) continue;
      if (!packet) {
        slot.mesh.visible = false;
        if (slot.trail) slot.trail.visible = false;
        continue;
      }
      const elapsed = now - packet.startedAt;
      const t = Math.min(1, elapsed / PACKET_LIFETIME_MS);
      // Ease-in-out for a satisfying curve along the trajectory.
      const eased = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;

      // Slight arc by lifting the midpoint up in Y.
      const lift =
        Math.sin(eased * Math.PI) *
        0.6 *
        packet.from.distanceTo(packet.to) *
        0.08;

      slot.mesh.visible = true;
      slot.mesh.position.lerpVectors(packet.from, packet.to, eased);
      slot.mesh.position.y += lift;

      // Fade alpha as it nears its destination.
      const mat = slot.mesh.material as THREE.MeshBasicMaterial;
      const alpha = t < 0.85 ? 1 : 1 - (t - 0.85) / 0.15;
      mat.opacity = 0.95 * alpha;
      (slot.mesh.material as THREE.MeshBasicMaterial).color.copy(packet.color);

      if (slot.trail) {
        slot.trail.visible = true;
        slot.trail.position.copy(slot.mesh.position);
        const trailMat = slot.trail.material as THREE.MeshBasicMaterial;
        trailMat.color.copy(packet.color);
        trailMat.opacity = 0.35 * alpha;
      }
    }
  });

  return (
    <group ref={groupRef}>
      {meshes.map((slot, i) => (
        <group key={i}>
          <mesh ref={(m) => { slot.mesh = m; }} visible={false}>
            <sphereGeometry args={[0.09, 10, 8]} />
            <meshBasicMaterial
              transparent
              opacity={0.95}
              depthWrite={false}
              blending={THREE.AdditiveBlending}
            />
          </mesh>
          <mesh ref={(m) => { slot.trail = m; }} visible={false}>
            <sphereGeometry args={[0.22, 10, 8]} />
            <meshBasicMaterial
              transparent
              opacity={0.35}
              depthWrite={false}
              blending={THREE.AdditiveBlending}
            />
          </mesh>
        </group>
      ))}
    </group>
  );
}

/**
 * Helper: compute live positions for each agent given the placements that
 * UniverseScene already calculates. Used to feed MessagePackets without
 * duplicating the orbit math.
 *
 * NOTE: This snapshots positions at one moment. Packets that take longer
 * than ~2s appear to "miss" the (now moved) target — that's fine; it reads
 * as a comet pointed at where the agent *was*, which is more honest than
 * faking continuous tracking.
 */
export function snapshotPlacements(
  agents: AgentInfo[],
  layoutFn: (a: AgentInfo) => { x: number; y: number; z: number } | null,
): Map<string, { x: number; y: number; z: number }> {
  const m = new Map<string, { x: number; y: number; z: number }>();
  for (const a of agents) {
    const p = layoutFn(a);
    if (p) m.set(a.agent_id, p);
  }
  return m;
}
