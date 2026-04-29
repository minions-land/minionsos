# Phase 2: Components + Solar System (Tasks 6–8)

### Task 6: Shared Components

**Files:**
- Create: `minions-viz-v2/src/web/components/TopBar.tsx`
- Create: `minions-viz-v2/src/web/components/BottomDock.tsx`
- Create: `minions-viz-v2/src/web/components/GruPicker.tsx`
- Create: `minions-viz-v2/src/web/components/ProjectPicker.tsx`
- Create: `minions-viz-v2/src/web/components/SlideOutPanel.tsx`
- Create: `minions-viz-v2/src/web/components/TaskDetailModal.tsx`
- Create: `minions-viz-v2/src/web/components/GlobalSearch.tsx`
- Create: `minions-viz-v2/src/web/components/ToastContainer.tsx`
- Create: `minions-viz-v2/src/web/components/EmptyState.tsx`

Reference: `docs/superpowers/specs/2026-04-28-minionsviz-v2/shared-components.md`

- [ ] **Step 1: Create EmptyState.tsx**

Reusable empty state with icon + message. All empty states fade in on mount.

```tsx
import { useEffect, useState, type ReactNode } from "react";

interface Props { icon: ReactNode; message: string; children?: ReactNode; }

export default function EmptyState({ icon, message, children }: Props) {
  const [visible, setVisible] = useState(false);
  useEffect(() => { requestAnimationFrame(() => setVisible(true)); }, []);
  return (
    <div className="empty-state" style={{ opacity: visible ? 1 : 0, transform: visible ? "translateY(0)" : "translateY(12px)", transition: "opacity 300ms var(--ease-out), transform 300ms var(--ease-out)" }}>
      <div style={{ opacity: 0.35 }}>{icon}</div>
      <p>{message}</p>
      {children}
    </div>
  );
}
```

- [ ] **Step 2: Create ToastContainer.tsx**

Adapt from `minions-viz/src/web/components/ToastContainer.tsx`. Restyle with dark theme: frosted glass background (`var(--panel-bg)` + backdrop blur), slide-up animation, auto-dismiss fade-out. Keep the same `toast()` export API.

- [ ] **Step 3: Create TopBar.tsx**

Height 48px, frosted glass. Contents left→right: "MinionsVIZ" logo text (Space Grotesk 600, subtle glow), Gru selector dropdown pill, Project selector dropdown pill, spacer, connection indicator (green/red dot + text), Cmd+K search hint, export button.

Props: `tab`, `grus`, `selectedGruId`, `selectedPort`, `connected`, `agentCount`, `taskCount`, `onSearch`, `onExport`.

Dropdowns: positioned absolute below the pill, frosted glass panel, slide-down 250ms + fade-in. Each Gru item shows label + live/stale dot. Each project item shows name + port + status badge.

- [ ] **Step 4: Create BottomDock.tsx**

Fixed bottom bar, 56px height, frosted glass. Three icon buttons using Phosphor icons:
- `Planet` icon → Solar System page
- `ChartBar` icon → Dashboard page
- `Terminal` icon → Terminal Hub page

Active page icon glows in gold (`var(--role-gru)`), label fully opaque. Inactive at 40% opacity. Active indicator slides horizontally between icons (animated left position).

```tsx
import { Planet, ChartBar, Terminal } from "@phosphor-icons/react";

export type Page = "solar" | "dashboard" | "terminal";
interface Props { page: Page; onNavigate: (p: Page) => void; }

const ITEMS: { key: Page; icon: typeof Planet; label: string }[] = [
  { key: "solar", icon: Planet, label: "Solar System" },
  { key: "dashboard", icon: ChartBar, label: "Dashboard" },
  { key: "terminal", icon: Terminal, label: "Terminal" },
];
```

- [ ] **Step 5: Create GruPicker.tsx and ProjectPicker.tsx**

Adapt from `minions-viz/src/web/components/GruPicker.tsx` and `ProjectPicker.tsx`. Restyle with dark theme: `surface-card` becomes frosted glass cards on dark background. Live Grus get gold border glow. Project cards show role-colored left border. Staggered fade-in animation (80ms delay per card).

- [ ] **Step 6: Create SlideOutPanel.tsx**

Right-side panel, 420px wide (90vw on mobile). Slides in from right 350ms, out 250ms. Frosted glass bg + 2px left border in role color. Close on X, click-outside, or Escape.

```tsx
interface Props {
  open: boolean;
  onClose: () => void;
  accentColor?: string;
  children: React.ReactNode;
}
```

Render a scrim (`rgba(0,0,0,0.4)`) behind the panel. Panel content scrollable. Animate with CSS transform + transition.

- [ ] **Step 7: Create TaskDetailModal.tsx**

Centered modal, max-width 560px. Scrim + scale(0.95→1) + fade-in 250ms. Shows: task ID, status badge, initiator avatar, assigned avatar, domains as pills, full description, subtasks list, results, timeline. Close on X, scrim click, Escape.

Adapt structure from `minions-viz/src/web/components/TaskDetail.tsx`, restyle with dark theme tokens.

- [ ] **Step 8: Create GlobalSearch.tsx**

Cmd+K modal. Adapt from `minions-viz/src/web/components/GlobalSearch.tsx`. Restyle: dark frosted glass, mono font input, results grouped by Agents/Tasks/Messages. Arrow key navigation. Same appear/dismiss animation as TaskDetailModal.

- [ ] **Step 9: Verify build**

```bash
cd minions-viz-v2 && npx vite build
```

- [ ] **Step 10: Commit**

```bash
git add minions-viz-v2/src/web/components/
git commit -m "feat(viz-v2): add shared components (dock, panels, modals, pickers)"
```

---

### Task 7: Solar System Canvas Engine

**Files:**
- Create: `minions-viz-v2/src/web/utils/canvasUtils.ts`
- Create: `minions-viz-v2/src/web/pages/solar-system/useOrbitalEngine.ts`
- Create: `minions-viz-v2/src/web/pages/solar-system/SolarSystemCanvas.tsx`

Reference: `docs/superpowers/specs/2026-04-28-minionsviz-v2/page-solar-system.md`

- [ ] **Step 1: Create canvasUtils.ts**

Low-level Canvas drawing helpers:

```typescript
export function drawEllipse(ctx: CanvasRenderingContext2D, cx: number, cy: number, rx: number, ry: number, opts: { stroke: string; lineWidth: number; dash?: number[] }) {
  ctx.save();
  ctx.beginPath();
  ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
  ctx.strokeStyle = opts.stroke;
  ctx.lineWidth = opts.lineWidth;
  if (opts.dash) ctx.setLineDash(opts.dash);
  ctx.stroke();
  ctx.restore();
}

export function drawGlow(ctx: CanvasRenderingContext2D, x: number, y: number, radius: number, color: string, intensity: number) {
  const grad = ctx.createRadialGradient(x, y, 0, x, y, radius);
  grad.addColorStop(0, color.replace(")", `,${intensity})`).replace("rgb", "rgba"));
  grad.addColorStop(1, "transparent");
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.fill();
}

export function drawBufferRing(ctx: CanvasRenderingContext2D, x: number, y: number, nodeRadius: number, thickness: number, color: string, rotation: number) {
  if (thickness <= 0) return;
  const ringRx = nodeRadius + 8 + thickness / 2;
  const ringRy = ringRx * 0.35;
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(rotation);
  ctx.beginPath();
  ctx.ellipse(0, 0, ringRx, ringRy, 0, 0, Math.PI * 2);
  ctx.strokeStyle = color;
  ctx.lineWidth = thickness;
  ctx.globalAlpha = 0.8;
  ctx.stroke();
  ctx.restore();
}

export function drawParticleTrail(ctx: CanvasRenderingContext2D, particles: { x: number; y: number; alpha: number; size: number; color: string }[]) {
  for (const p of particles) {
    ctx.globalAlpha = p.alpha;
    ctx.fillStyle = p.color;
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

export function drawMessageBeam(ctx: CanvasRenderingContext2D, from: { x: number; y: number }, to: { x: number; y: number }, progress: number, color: string) {
  const cp = { x: (from.x + to.x) / 2, y: Math.min(from.y, to.y) - 40 };
  const t = progress;
  const headX = (1 - t) * (1 - t) * from.x + 2 * (1 - t) * t * cp.x + t * t * to.x;
  const headY = (1 - t) * (1 - t) * from.y + 2 * (1 - t) * t * cp.y + t * t * to.y;

  ctx.save();
  ctx.beginPath();
  ctx.moveTo(from.x, from.y);
  ctx.quadraticCurveTo(cp.x, cp.y, headX, headY);
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.globalAlpha = 0.7;
  ctx.stroke();
  drawGlow(ctx, headX, headY, 6, color, 0.8);
  ctx.restore();
}
```

- [ ] **Step 2: Create useOrbitalEngine.ts**

This hook manages all orbital state: planet positions, angles, speeds, buffer ring rotations, message beams, background stars, and mouse-driven particles.

```typescript
import { useRef, useCallback, useMemo } from "react";
import type { AgentInfo, Task } from "@shared/types";
import { getRoleIdentity, bufferRingStyle, ROLES } from "../../utils/roleIdentity";

export interface OrbitalState {
  planets: PlanetState[];
  star: StarState;
  beams: BeamState[];
  bgStars: BgStar[];
  mouseTrail: Particle[];
}

export interface PlanetState {
  key: string;
  angle: number;        // current orbital angle (radians)
  speed: number;        // current angular velocity (rad/ms), with inertia
  targetSpeed: number;  // target speed based on activity
  x: number; y: number; // computed screen position
  scale: number;        // 0.75 (back) to 1.0 (front)
  opacity: number;      // 0.6 (back) to 1.0 (front)
  zFront: boolean;      // true if in front half of orbit
  orbitRx: number;      // orbit ellipse radiusX (px)
  orbitRy: number;      // orbit ellipse radiusY (px)
  bufferRingAngle: number;
  bufferRingSpeed: number;
  bufferCount: number;
  state: "active" | "sleeping" | "dismissed" | "spawning" | "dismissing";
  nodeAlpha: number;    // for spawn/dismiss fade, 0→1 or 1→0
  hovered: boolean;
  dragging: boolean;
  dragOffset: { x: number; y: number };
}

export interface StarState {
  x: number; y: number;
  coronaPhase: number;  // 0→2π pulsing
  bufferRingAngle: number;
  bufferRingSpeed: number;
  bufferCount: number;
  active: boolean;
}

export interface BeamState {
  from: string; to: string;
  progress: number; // 0→1
  color: string;
}

export interface BgStar { x: number; y: number; brightness: number; twinklePhase: number; }
export interface Particle { x: number; y: number; alpha: number; size: number; color: string; vx: number; vy: number; life: number; }
```

The hook exposes:
- `stateRef: MutableRefObject<OrbitalState>` — mutable ref updated each frame
- `tick(dt: number)` — advance all physics by dt milliseconds
- `resize(w: number, h: number)` — recompute orbit radii and center
- `syncAgents(agents: AgentInfo[])` — update planet states from store data
- `addBeam(from: string, to: string, color: string)` — trigger a message beam
- `setHovered(key: string | null)` — pause hovered planet
- `startDrag(key: string, offsetX: number, offsetY: number)` — begin drag
- `moveDrag(x: number, y: number)` — update drag position
- `endDrag()` — release with spring-back
- `addMouseParticles(x: number, y: number)` — star dust trail

Key physics in `tick(dt)`:
- Each planet: `speed += (targetSpeed - speed) * (1 - Math.exp(-dt / 800))` (inertia)
- If not hovered/dragging: `angle += speed * dt`
- Position: `x = cx + orbitRx * cos(angle)`, `y = cy + orbitRy * sin(angle)`
- Scale: `lerp(0.75, 1.0, (sin(angle) + 1) / 2)`
- Opacity: `lerp(0.6, 1.0, (sin(angle) + 1) / 2)`
- Buffer ring: `bufferRingAngle += (2π / bufferRingSpeed) * dt` (if speed > 0)
- Star corona: `coronaPhase += dt * 0.001`
- Beams: `progress += dt / 800`, remove when progress > 1
- Mouse particles: `alpha -= dt * 0.0025`, remove when alpha <= 0
- Background star twinkle: `twinklePhase += dt * 0.0005 * random`

- [ ] **Step 3: Create SolarSystemCanvas.tsx**

Canvas component that renders the background layer. Receives `stateRef` from the orbital engine and draws each frame.

```tsx
import { useRef, useEffect } from "react";
import { useAnimationFrame } from "../../hooks/useAnimationFrame";
import { drawEllipse, drawGlow, drawBufferRing, drawParticleTrail, drawMessageBeam } from "../../utils/canvasUtils";
import type { OrbitalState } from "./useOrbitalEngine";

interface Props {
  stateRef: React.MutableRefObject<OrbitalState>;
  tick: (dt: number) => void;
  width: number;
  height: number;
}

export default function SolarSystemCanvas({ stateRef, tick, width, height }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useAnimationFrame((dt) => {
    tick(dt);
    const ctx = canvasRef.current?.getContext("2d");
    if (!ctx) return;
    const s = stateRef.current;
    const dpr = window.devicePixelRatio || 1;
    ctx.clearRect(0, 0, width * dpr, height * dpr);
    ctx.save();
    ctx.scale(dpr, dpr);

    // 1. Background stars (twinkle)
    for (const star of s.bgStars) {
      const b = star.brightness * (0.7 + 0.3 * Math.sin(star.twinklePhase));
      ctx.fillStyle = `rgba(200,210,230,${b})`;
      ctx.beginPath();
      ctx.arc(star.x, star.y, 1, 0, Math.PI * 2);
      ctx.fill();
    }

    // 2. Orbital path ellipses (back half — behind star)
    // 3. Planets in back half (sorted by angle for z-order)
    // 4. Star glow + corona
    // 5. Star buffer ring
    // 6. Orbital path ellipses (front half)
    // 7. Planets in front half
    // 8. Planet buffer rings
    // 9. Message beams
    // 10. Mouse trail particles

    ctx.restore();
  });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
  }, [width, height]);

  return <canvas ref={canvasRef} style={{ width, height, position: "absolute", inset: 0 }} />;
}
```

The draw loop must render in z-order: back-half orbits → back-half planets → star → front-half orbits → front-half planets → beams → particles. Use `planet.zFront` to partition.

Implement all 10 draw steps fully. Each orbital path uses `drawEllipse`. Each planet position gets `drawGlow` for the role-color halo. Buffer rings use `drawBufferRing`. Star gets a multi-layer corona via nested `drawGlow` calls with varying radii and the `coronaPhase` modulating intensity.

- [ ] **Step 4: Verify build**

```bash
cd minions-viz-v2 && npx vite build
```

- [ ] **Step 5: Commit**

```bash
git add minions-viz-v2/src/web/utils/canvasUtils.ts minions-viz-v2/src/web/pages/solar-system/
git commit -m "feat(viz-v2): add solar system canvas engine with orbital mechanics"
```

---

### Task 8: Solar System HTML Overlay + Page

**Files:**
- Create: `minions-viz-v2/src/web/pages/solar-system/StarNode.tsx`
- Create: `minions-viz-v2/src/web/pages/solar-system/PlanetNode.tsx`
- Create: `minions-viz-v2/src/web/pages/solar-system/SolarSystemPage.tsx`

- [ ] **Step 1: Create StarNode.tsx**

HTML div positioned absolutely at the star's screen coordinates. Shows Gru crown avatar, project name label, golden glow ring via CSS box-shadow.

```tsx
import { Crown } from "@phosphor-icons/react";
import { ROLES } from "../../utils/roleIdentity";

interface Props { x: number; y: number; projectName: string; active: boolean; }

export default function StarNode({ x, y, projectName, active }: Props) {
  const gru = ROLES.gru;
  return (
    <div className="absolute pointer-events-auto cursor-pointer" style={{
      left: x - 40, top: y - 40, width: 80, height: 80,
      transition: "box-shadow 600ms var(--ease-out), opacity 600ms var(--ease-out)",
    }}>
      <div className="w-full h-full rounded-full flex items-center justify-center" style={{
        background: `radial-gradient(circle, rgba(${gru.colorRgb},0.15), transparent 70%)`,
        boxShadow: active
          ? `0 0 30px rgba(${gru.colorRgb},0.4), 0 0 60px rgba(${gru.colorRgb},0.2)`
          : `0 0 15px rgba(${gru.colorRgb},0.2)`,
      }}>
        <Crown size={32} weight="fill" color={gru.color} />
      </div>
      <div className="absolute -bottom-5 left-1/2 -translate-x-1/2 whitespace-nowrap text-center">
        <div className="font-mono text-[10px] font-semibold" style={{ color: gru.color }}>{projectName}</div>
        <div className="font-mono text-[9px]" style={{ color: "var(--muted)" }}>GRU</div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create PlanetNode.tsx**

HTML div for each role planet. Positioned at computed screen coords. Shows role icon, name label, state indicator. Handles hover (pointer events) and drag (mousedown/mousemove/mouseup).

Props: `roleKey`, `x`, `y`, `scale`, `opacity`, `state`, `hovered`, `bufferCount`, `onHover`, `onLeave`, `onClick`, `onDragStart`.

The node scales and fades based on 2.5D position. When `state === "dismissed"`, render as ghost outline (border only, 20% opacity). Spawning/dismissing states use CSS transitions for scale and opacity.

- [ ] **Step 3: Create SolarSystemPage.tsx**

Page wrapper that composes everything:

1. Uses `useStore()` to get agents, tasks, messages, project info
2. Initializes `useOrbitalEngine()` with agent data
3. Tracks container size via `ResizeObserver`
4. Renders `SolarSystemCanvas` (full-size, absolute positioned)
5. Renders HTML overlay with `StarNode` + `PlanetNode` array (absolute positioned, synced to engine coords each frame)
6. Renders `SlideOutPanel` for role detail (opens on planet click)
7. Handles mouse events: mousemove for hover detection + star dust trail, mousedown/mouseup for drag

Mouse event flow:
- `onMouseMove` on container → check proximity to each planet → set hovered → add mouse trail particles
- `onMouseDown` on PlanetNode → start drag
- `onMouseMove` during drag → update drag position
- `onMouseUp` → end drag (spring back)
- `onClick` on PlanetNode → open SlideOutPanel with role detail
- `onWheel` → zoom (scale 0.5x to 2.0x, applied as CSS transform on the container)

SlideOutPanel content for a role: header (avatar + name + state + buffer), last 5 messages, recent tasks, scratchpad preview, "Open in Terminal Hub →" link.

Sync loop: on each `useAnimationFrame` tick, read `stateRef.current.planets` positions and update the HTML node positions via refs (not state, to avoid React re-renders at 60fps). Use `ref.current.style.transform = ...` directly.

- [ ] **Step 4: Verify build**

```bash
cd minions-viz-v2 && npx vite build
```

- [ ] **Step 5: Commit**

```bash
git add minions-viz-v2/src/web/pages/solar-system/
git commit -m "feat(viz-v2): add solar system page with 2.5D orbital topology"
```
