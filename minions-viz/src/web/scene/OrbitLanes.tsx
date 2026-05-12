import { useMemo } from "react";
import * as THREE from "three";

export interface Lane {
  radius: number;
  color: string;
  tiltX: number;
  tiltZ: number;
  label?: string;
}

/**
 * Orbit rings. Each lane's ring sits in a plane tilted by tiltX about X and
 * tiltZ about Z, and spheres in that lane use the same transform so they
 * always ride *on* the ring.
 */
export default function OrbitLanes({ lanes }: { lanes: Lane[] }) {
  const rings = useMemo(() => {
    return lanes.map((lane) => {
      const segments = 96;
      const geo = new THREE.BufferGeometry();
      const positions = new Float32Array((segments + 1) * 3);
      for (let i = 0; i <= segments; i++) {
        const a = (i / segments) * Math.PI * 2;
        positions[i * 3 + 0] = Math.cos(a) * lane.radius;
        positions[i * 3 + 1] = 0;
        positions[i * 3 + 2] = Math.sin(a) * lane.radius;
      }
      geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      const mat = new THREE.LineBasicMaterial({
        color: lane.color,
        transparent: true,
        opacity: 0.22,
        depthWrite: false,
      });
      const line = new THREE.Line(geo, mat);
      const matrix = new THREE.Matrix4()
        .makeRotationX(lane.tiltX)
        .multiply(new THREE.Matrix4().makeRotationZ(lane.tiltZ));
      line.applyMatrix4(matrix);
      return line;
    });
  }, [lanes]);

  return (
    <group>
      {rings.map((r, i) => (
        <primitive key={i} object={r} />
      ))}
    </group>
  );
}
