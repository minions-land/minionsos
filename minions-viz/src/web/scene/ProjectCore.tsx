import { useRef, useMemo } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";

interface Props {
  projectName: string;
  active: boolean;
}

/**
 * Central "project core" — the Gru star. Layered: inner molten sphere with
 * emissive surface + animated normal-offset, a wide radiant halo, and a
 * cold outer ring at an inclination. Label floats below.
 */
export default function ProjectCore({ projectName, active }: Props) {
  const coreRef = useRef<THREE.Mesh>(null);
  const glowRef = useRef<THREE.Mesh>(null);
  const ringRef = useRef<THREE.Mesh>(null);
  const discRef = useRef<THREE.Mesh>(null);
  const crownRef = useRef<THREE.Group>(null);

  const corona = useMemo(() => {
    // Generate a soft procedural sphere for corona — displacement texture is
    // avoided (kept dependency-light).
    return null;
  }, []);

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    const pulse = 1 + Math.sin(t * 1.6) * 0.04;
    if (coreRef.current) coreRef.current.scale.setScalar(pulse);
    if (glowRef.current) {
      const gp = 1 + Math.sin(t * 0.9) * 0.08;
      glowRef.current.scale.setScalar(gp);
      const mat = glowRef.current.material as THREE.MeshBasicMaterial;
      mat.opacity = 0.18 + (Math.sin(t * 0.7) * 0.5 + 0.5) * 0.05;
    }
    if (ringRef.current) ringRef.current.rotation.z = t * 0.12;
    if (discRef.current) discRef.current.rotation.z = -t * 0.06;
    if (crownRef.current) crownRef.current.rotation.y = t * 0.4;
  });

  const gold = "#F59E0B";
  const amber = "#FCD34D";
  const dim = "#8b6914";
  const color = active ? gold : dim;

  return (
    <group>
      {/* Core */}
      <mesh ref={coreRef}>
        <sphereGeometry args={[0.95, 32, 24]} />
        <meshStandardMaterial
          color={amber}
          emissive={color}
          emissiveIntensity={1.8}
          roughness={0.35}
          metalness={0.15}
        />
      </mesh>

      {/* Corona / inner glow */}
      <mesh ref={glowRef}>
        <sphereGeometry args={[1.35, 18, 14]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={0.18}
          depthWrite={false}
        />
      </mesh>

      {/* Cold outer ring disk — broad ring Saturn-style. */}
      <mesh ref={discRef} rotation={[Math.PI / 2.2, 0, 0.3]}>
        <ringGeometry args={[1.85, 2.8, 56]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={0.22}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>

      {/* Thin bright ring */}
      <mesh ref={ringRef} rotation={[Math.PI / 2.4, 0, 0]}>
        <ringGeometry args={[1.7, 1.82, 56]} />
        <meshBasicMaterial
          color={amber}
          transparent
          opacity={0.7}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>

      {/* Crown: small orbiting satellites marking compass points. */}
      <group ref={crownRef}>
        {[0, Math.PI / 2, Math.PI, (3 * Math.PI) / 2].map((a, i) => (
          <mesh
            key={i}
            position={[Math.cos(a) * 1.35, 0.02 * Math.sin(a), Math.sin(a) * 1.35]}
          >
            <sphereGeometry args={[0.04, 10, 10]} />
            <meshBasicMaterial color={amber} />
          </mesh>
        ))}
      </group>

      {/* Project name */}
      <Html position={[0, -1.85, 0]} center distanceFactor={8}>
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 14,
            padding: "5px 12px",
            background: "rgba(8,11,20,0.78)",
            border: `1px solid ${color}55`,
            borderRadius: 6,
            color: amber,
            whiteSpace: "nowrap",
            letterSpacing: "0.05em",
            pointerEvents: "none",
            textShadow: "0 0 8px rgba(245,158,11,0.35)",
          }}
        >
          ★ {projectName}
        </div>
      </Html>
    </group>
  );
}
