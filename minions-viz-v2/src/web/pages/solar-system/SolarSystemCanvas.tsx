import React, { useRef, useEffect } from "react";
import { useAnimationFrame } from "../../hooks/useAnimationFrame";
import {
  drawEllipse,
  drawGlow,
  drawBufferRing,
  drawParticleTrail,
  drawMessageBeam,
  drawStarCorona,
} from "../../utils/canvasUtils";
import { bufferRingStyle } from "../../utils/roleIdentity";
import type { OrbitalState } from "./useOrbitalEngine";

interface Props {
  stateRef: React.MutableRefObject<OrbitalState>;
  tick: (dt: number) => void;
  width: number;
  height: number;
}

export function SolarSystemCanvas({ stateRef, tick, width, height }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Handle DPR and canvas sizing
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
  }, [width, height]);

  useAnimationFrame((dt) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    tick(dt);

    const dpr = window.devicePixelRatio || 1;
    const s = stateRef.current;

    ctx.save();
    ctx.scale(dpr, dpr);

    // 1. Clear
    ctx.clearRect(0, 0, width, height);

    // 2. Background stars
    for (const bg of s.bgStars) {
      const alpha = bg.brightness * (0.6 + 0.4 * Math.sin(bg.twinklePhase));
      ctx.globalAlpha = alpha;
      ctx.fillStyle = "#fff";
      ctx.beginPath();
      ctx.arc(bg.x, bg.y, 0.8 + bg.brightness * 0.6, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;

    // Separate planets into back and front
    const backPlanets = s.planets.filter((p) => !p.zFront);
    const frontPlanets = s.planets.filter((p) => p.zFront);

    // 3. Orbital path ellipses for BACK-HALF planets
    for (const p of backPlanets) {
      const dash = p.state === "sleeping" ? [4, 8] : undefined;
      drawEllipse(ctx, s.cx, s.cy, p.orbitRx, p.orbitRy, {
        stroke: "rgba(255,255,255,0.06)",
        lineWidth: 1,
        dash,
      });
    }

    // 4. Planet glows for BACK-HALF
    for (const p of backPlanets) {
      if (p.nodeAlpha < 0.05) continue;
      const radius = 24 * p.scale;
      ctx.globalAlpha = p.opacity * p.nodeAlpha * 0.7;
      drawGlow(ctx, p.x, p.y, radius * 2, p.colorRgb, p.opacity);
      ctx.globalAlpha = 1;
    }

    // 5. Buffer rings for BACK-HALF
    for (const p of backPlanets) {
      const brs = bufferRingStyle(p.bufferCount);
      if (brs.thickness > 0) {
        ctx.globalAlpha = p.opacity * p.nodeAlpha;
        drawBufferRing(ctx, p.x, p.y, 24 * p.scale, brs.thickness, brs.color, p.bufferRingAngle);
        ctx.globalAlpha = 1;
      }
    }

    // 6. Star corona
    drawStarCorona(ctx, s.star.x, s.star.y, 40, s.star.coronaPhase, s.star.colorRgb);

    // 7. Star buffer ring
    const starBrs = bufferRingStyle(s.star.bufferCount);
    if (starBrs.thickness > 0) {
      drawBufferRing(ctx, s.star.x, s.star.y, 40, starBrs.thickness, starBrs.color, s.star.bufferRingAngle);
    }

    // 8. Orbital path ellipses for FRONT-HALF planets
    for (const p of frontPlanets) {
      const dash = p.state === "sleeping" ? [4, 8] : undefined;
      drawEllipse(ctx, s.cx, s.cy, p.orbitRx, p.orbitRy, {
        stroke: "rgba(255,255,255,0.08)",
        lineWidth: 1,
        dash,
      });
    }

    // 9. Planet glows for FRONT-HALF
    for (const p of frontPlanets) {
      if (p.nodeAlpha < 0.05) continue;
      const radius = 24 * p.scale;
      ctx.globalAlpha = p.opacity * p.nodeAlpha;
      drawGlow(ctx, p.x, p.y, radius * 2.5, p.colorRgb, p.opacity);
      ctx.globalAlpha = 1;
    }

    // 10. Buffer rings for FRONT-HALF
    for (const p of frontPlanets) {
      const brs = bufferRingStyle(p.bufferCount);
      if (brs.thickness > 0) {
        ctx.globalAlpha = p.opacity * p.nodeAlpha;
        drawBufferRing(ctx, p.x, p.y, 24 * p.scale, brs.thickness, brs.color, p.bufferRingAngle);
        ctx.globalAlpha = 1;
      }
    }

    // 11. Message beams
    for (const beam of s.beams) {
      drawMessageBeam(
        ctx,
        { x: beam.fromX, y: beam.fromY },
        { x: beam.toX, y: beam.toY },
        beam.progress,
        beam.color,
      );
    }

    // 12. Mouse trail particles
    if (s.mouseTrail.length > 0) {
      drawParticleTrail(ctx, s.mouseTrail);
    }

    ctx.restore();
  });

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        width: `${width}px`,
        height: `${height}px`,
        pointerEvents: "none",
      }}
    />
  );
}
