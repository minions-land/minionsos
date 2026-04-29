import { useRef, useCallback } from "react";
import { ROLES, getRoleIdentity, bufferRingStyle } from "../../utils/roleIdentity";
import type { AgentInfo } from "@shared/types";

// ── Types ───────────────────────────────────────────────────────────

export interface PlanetState {
  key: string;
  angle: number;
  speed: number;
  targetSpeed: number;
  x: number;
  y: number;
  scale: number;
  opacity: number;
  zFront: boolean;
  orbitRx: number;
  orbitRy: number;
  bufferRingAngle: number;
  bufferCount: number;
  state: "active" | "sleeping" | "dismissed";
  nodeAlpha: number;
  hovered: boolean;
  dragging: boolean;
  dragX: number;
  dragY: number;
  color: string;
  colorRgb: string;
  label: string;
}

export interface StarState {
  x: number;
  y: number;
  coronaPhase: number;
  bufferRingAngle: number;
  bufferCount: number;
  active: boolean;
  color: string;
  colorRgb: string;
}

export interface BeamState {
  fromKey: string;
  toKey: string;
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
  progress: number;
  color: string;
}

export interface BgStar {
  x: number;
  y: number;
  brightness: number;
  twinklePhase: number;
}

export interface Particle {
  x: number;
  y: number;
  alpha: number;
  size: number;
  color: string;
  vx: number;
  vy: number;
}

export interface OrbitalState {
  cx: number;
  cy: number;
  planets: PlanetState[];
  star: StarState;
  beams: BeamState[];
  bgStars: BgStar[];
  mouseTrail: Particle[];
}

// ── Helpers ─────────────────────────────────────────────────────────

const TWO_PI = Math.PI * 2;

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t;
}

function makeBgStars(w: number, h: number, count = 200): BgStar[] {
  const stars: BgStar[] = [];
  for (let i = 0; i < count; i++) {
    stars.push({
      x: Math.random() * w,
      y: Math.random() * h,
      brightness: 0.3 + Math.random() * 0.5,
      twinklePhase: Math.random() * TWO_PI,
    });
  }
  return stars;
}

const PLANET_ROLES = Object.values(ROLES).filter((r) => r.orbitIndex > 0);

function initialPlanets(cx: number, cy: number, w: number, h: number): PlanetState[] {
  const minDim = Math.min(w, h) * 0.85;
  return PLANET_ROLES.map((role) => {
    const orbitRx = minDim * 0.12 * role.orbitIndex;
    const orbitRy = orbitRx * 0.4;
    const angle = (role.orbitIndex - 1) * (TWO_PI / 6);
    const x = cx + orbitRx * Math.cos(angle);
    const y = cy + orbitRy * Math.sin(angle);
    const sinA = Math.sin(angle);
    const depthT = (sinA + 1) / 2;
    return {
      key: role.key,
      angle,
      speed: 0,
      targetSpeed: 0,
      x,
      y,
      scale: lerp(0.75, 1.0, depthT),
      opacity: lerp(0.6, 1.0, depthT),
      zFront: sinA > 0,
      orbitRx,
      orbitRy,
      bufferRingAngle: 0,
      bufferCount: 0,
      state: "sleeping" as const,
      nodeAlpha: 0.2,
      hovered: false,
      dragging: false,
      dragX: 0,
      dragY: 0,
      color: role.color,
      colorRgb: role.colorRgb,
      label: role.label,
    };
  });
}

function initialStar(cx: number, cy: number): StarState {
  const gru = ROLES.gru;
  return {
    x: cx,
    y: cy,
    coronaPhase: 0,
    bufferRingAngle: 0,
    bufferCount: 0,
    active: false,
    color: gru.color,
    colorRgb: gru.colorRgb,
  };
}

// ── Hook ────────────────────────────────────────────────────────────

export function useOrbitalEngine() {
  const stateRef = useRef<OrbitalState>({
    cx: 0,
    cy: 0,
    planets: [],
    star: initialStar(0, 0),
    beams: [],
    bgStars: [],
    mouseTrail: [],
  });

  const tick = useCallback((dt: number) => {
    const s = stateRef.current;

    // Planets
    for (const p of s.planets) {
      // Inertia
      p.speed += (p.targetSpeed - p.speed) * (1 - Math.exp(-dt / 800));

      // Orbital motion
      if (!p.hovered && !p.dragging) {
        p.angle += p.speed * dt;
        p.x = s.cx + p.orbitRx * Math.cos(p.angle);
        p.y = s.cy + p.orbitRy * Math.sin(p.angle);
      }

      // 2.5D depth
      const sinA = Math.sin(p.angle);
      const depthT = (sinA + 1) / 2;
      p.scale = lerp(0.75, 1.0, depthT);
      p.opacity = lerp(0.6, 1.0, depthT);
      p.zFront = sinA > 0;

      // Buffer ring rotation
      const brs = bufferRingStyle(p.bufferCount);
      if (brs.speed > 0) {
        p.bufferRingAngle += (TWO_PI / brs.speed) * (dt / 1000);
      }

      // nodeAlpha transition
      const alphaTarget = p.state === "dismissed" ? 0.2 : 1.0;
      p.nodeAlpha += (alphaTarget - p.nodeAlpha) * Math.min(dt * 0.003, 1);
    }

    // Star
    s.star.coronaPhase += dt * 0.001;
    const starBrs = bufferRingStyle(s.star.bufferCount);
    if (starBrs.speed > 0) {
      s.star.bufferRingAngle += (TWO_PI / starBrs.speed) * (dt / 1000);
    }

    // Beams
    for (let i = s.beams.length - 1; i >= 0; i--) {
      s.beams[i].progress += dt / 800;
      if (s.beams[i].progress > 1.2) {
        s.beams.splice(i, 1);
      }
    }

    // Background stars
    for (const bg of s.bgStars) {
      bg.twinklePhase += dt * 0.0005 * (0.5 + bg.brightness);
    }

    // Mouse trail particles
    for (let i = s.mouseTrail.length - 1; i >= 0; i--) {
      const pt = s.mouseTrail[i];
      pt.x += pt.vx * dt;
      pt.y += pt.vy * dt;
      pt.alpha -= dt * 0.003;
      if (pt.alpha <= 0) {
        s.mouseTrail.splice(i, 1);
      }
    }
  }, []);

  const resize = useCallback((w: number, h: number) => {
    const s = stateRef.current;
    s.cx = w / 2;
    s.cy = h / 2;
    s.star.x = s.cx;
    s.star.y = s.cy;

    const minDim = Math.min(w, h) * 0.85;
    for (const p of s.planets) {
      const role = getRoleIdentity(p.key);
      p.orbitRx = minDim * 0.12 * role.orbitIndex;
      p.orbitRy = p.orbitRx * 0.4;
      if (!p.dragging) {
        p.x = s.cx + p.orbitRx * Math.cos(p.angle);
        p.y = s.cy + p.orbitRy * Math.sin(p.angle);
      }
    }

    s.bgStars = makeBgStars(w, h);

    // Initialize planets if empty (first resize)
    if (s.planets.length === 0) {
      s.planets = initialPlanets(s.cx, s.cy, w, h);
    }
  }, []);

  const syncAgents = useCallback((agents: AgentInfo[], gruAgent?: AgentInfo) => {
    const s = stateRef.current;

    // Sync Gru star
    if (gruAgent) {
      s.star.active = true;
      s.star.bufferCount = 0; // updated if buffer info available
    }

    // Sync planets
    for (const p of s.planets) {
      const agent = agents.find(
        (a) => a.agent_id.toLowerCase().includes(p.key) || a.name.toLowerCase().includes(p.key),
      );
      if (agent) {
        // Determine state from agent info
        const wasState = p.state;
        p.state = "active";
        p.bufferCount = 0;

        const role = getRoleIdentity(p.key);
        const basePeriod = role.baseOrbitPeriod;
        p.targetSpeed = TWO_PI / (basePeriod * 1000);

        // If newly appeared, keep existing angle
        if (wasState === "dismissed") {
          p.nodeAlpha = 0.2; // will lerp up
        }
      } else {
        // No matching agent — check if it was previously active
        if (p.state === "active") {
          p.state = "sleeping";
          const role = getRoleIdentity(p.key);
          p.targetSpeed = (TWO_PI / (role.baseOrbitPeriod * 1000)) * 0.05;
        }
      }
    }
  }, []);

  const addBeam = useCallback((fromKey: string, toKey: string, color: string) => {
    const s = stateRef.current;
    const fromNode =
      fromKey === "gru" ? s.star : s.planets.find((p) => p.key === fromKey);
    const toNode =
      toKey === "gru" ? s.star : s.planets.find((p) => p.key === toKey);
    if (!fromNode || !toNode) return;
    s.beams.push({
      fromKey,
      toKey,
      fromX: fromNode.x,
      fromY: fromNode.y,
      toX: toNode.x,
      toY: toNode.y,
      progress: 0,
      color,
    });
  }, []);

  const setHovered = useCallback((key: string | null) => {
    const s = stateRef.current;
    for (const p of s.planets) {
      p.hovered = p.key === key;
    }
  }, []);

  const startDrag = useCallback((key: string) => {
    const s = stateRef.current;
    const p = s.planets.find((pl) => pl.key === key);
    if (p) {
      p.dragging = true;
      p.dragX = p.x;
      p.dragY = p.y;
    }
  }, []);

  const moveDrag = useCallback((x: number, y: number) => {
    const s = stateRef.current;
    const p = s.planets.find((pl) => pl.dragging);
    if (p) {
      p.dragX = x;
      p.dragY = y;
      p.x = x;
      p.y = y;
    }
  }, []);

  const endDrag = useCallback(() => {
    const s = stateRef.current;
    const p = s.planets.find((pl) => pl.dragging);
    if (p) {
      p.dragging = false;
      // Snap angle to current position for smooth resume
      p.angle = Math.atan2(p.y - s.cy, p.x - s.cx);
    }
  }, []);

  const addMouseParticles = useCallback((x: number, y: number) => {
    const s = stateRef.current;
    const count = 5 + Math.floor(Math.random() * 3);
    for (let i = 0; i < count; i++) {
      const a = Math.random() * TWO_PI;
      const spd = 0.01 + Math.random() * 0.03;
      s.mouseTrail.push({
        x,
        y,
        alpha: 0.4 + Math.random() * 0.3,
        size: 1 + Math.random() * 1.5,
        color: "rgba(245,158,11,0.6)",
        vx: Math.cos(a) * spd,
        vy: Math.sin(a) * spd,
      });
    }
  }, []);

  return {
    stateRef,
    tick,
    resize,
    syncAgents,
    addBeam,
    setHovered,
    startDrag,
    moveDrag,
    endDrag,
    addMouseParticles,
  };
}
