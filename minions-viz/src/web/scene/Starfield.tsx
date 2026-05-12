import { useMemo, useRef } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";

/**
 * Multi-layer nebula field: three shells of colored stars with different
 * drift speeds, plus soft directional glows to break the flat black.
 */
export default function Nebula() {
  const farRef = useRef<THREE.Points>(null);
  const midRef = useRef<THREE.Points>(null);
  const dustRef = useRef<THREE.Points>(null);

  const far = useMemo(() => makeShell(900, 70, 120, [
    "#93c5fd",
    "#a78bfa",
    "#f0abfc",
    "#fcd34d",
  ], 0.08), []);
  const mid = useMemo(() => makeShell(420, 35, 65, [
    "#67e8f9",
    "#bae6fd",
    "#ddd6fe",
    "#fde68a",
  ], 0.14), []);
  const dust = useMemo(() => makeShell(220, 12, 25, [
    "#a5f3fc",
    "#cffafe",
    "#fef3c7",
  ], 0.22), []);

  useFrame((_state, delta) => {
    if (farRef.current) farRef.current.rotation.y += delta * 0.004;
    if (midRef.current) midRef.current.rotation.y -= delta * 0.009;
    if (dustRef.current) dustRef.current.rotation.y += delta * 0.02;
  });

  return (
    <group>
      <points ref={farRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            count={far.positions.length / 3}
            array={far.positions}
            itemSize={3}
          />
          <bufferAttribute
            attach="attributes-color"
            count={far.colors.length / 3}
            array={far.colors}
            itemSize={3}
          />
        </bufferGeometry>
        <pointsMaterial
          vertexColors
          size={0.5}
          sizeAttenuation
          transparent
          opacity={0.85}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </points>
      <points ref={midRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            count={mid.positions.length / 3}
            array={mid.positions}
            itemSize={3}
          />
          <bufferAttribute
            attach="attributes-color"
            count={mid.colors.length / 3}
            array={mid.colors}
            itemSize={3}
          />
        </bufferGeometry>
        <pointsMaterial
          vertexColors
          size={0.22}
          sizeAttenuation
          transparent
          opacity={0.95}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </points>
      <points ref={dustRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            count={dust.positions.length / 3}
            array={dust.positions}
            itemSize={3}
          />
          <bufferAttribute
            attach="attributes-color"
            count={dust.colors.length / 3}
            array={dust.colors}
            itemSize={3}
          />
        </bufferGeometry>
        <pointsMaterial
          vertexColors
          size={0.08}
          sizeAttenuation
          transparent
          opacity={0.6}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </points>
    </group>
  );
}

function makeShell(
  count: number,
  rMin: number,
  rMax: number,
  palette: string[],
  tintStrength: number,
) {
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const pal = palette.map((h) => new THREE.Color(h));
  for (let i = 0; i < count; i++) {
    const r = rMin + Math.random() * (rMax - rMin);
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    positions[i * 3 + 0] = r * Math.sin(phi) * Math.cos(theta);
    positions[i * 3 + 1] = r * Math.cos(phi) * 0.55;
    positions[i * 3 + 2] = r * Math.sin(phi) * Math.sin(theta);
    const c = pal[Math.floor(Math.random() * pal.length)];
    const t = 0.3 + Math.random() * tintStrength * 2;
    colors[i * 3 + 0] = c.r * t;
    colors[i * 3 + 1] = c.g * t;
    colors[i * 3 + 2] = c.b * t;
  }
  return { positions, colors };
}
