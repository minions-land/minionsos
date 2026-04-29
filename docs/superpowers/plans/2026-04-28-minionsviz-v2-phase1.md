# Phase 1: Foundation (Tasks 1–5)

### Task 1: Project Scaffolding

**Files:**
- Create: `minions-viz-v2/package.json`
- Create: `minions-viz-v2/vite.config.ts`
- Create: `minions-viz-v2/tsconfig.json`
- Create: `minions-viz-v2/tsconfig.server.json`
- Create: `minions-viz-v2/tailwind.config.js`
- Create: `minions-viz-v2/postcss.config.js`
- Create: `minions-viz-v2/index.html`
- Create: `minions-viz-v2/src/web/env.d.ts`
- Create: `minions-viz-v2/src/web/main.tsx`

- [ ] **Step 1: Create package.json**

```json
{
  "name": "minions-viz-v2",
  "version": "0.1.0",
  "description": "MinionsVIZ V2 — Mission Control Observatory for MinionsOS",
  "type": "module",
  "scripts": {
    "dev": "concurrently \"npm run dev:server\" \"npm run dev:web\"",
    "dev:server": "tsx watch src/server/index.ts",
    "dev:web": "vite",
    "build": "vite build && tsc --project tsconfig.server.json",
    "start": "npx tsx src/server/index.ts"
  },
  "dependencies": {
    "@phosphor-icons/react": "^2.1.0",
    "@xyflow/react": "^12.0.0",
    "cors": "^2.8.5",
    "dagre": "^0.8.5",
    "express": "^4.21.0",
    "ws": "^8.18.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "xterm": "^5.3.0",
    "xterm-addon-fit": "^0.8.0"
  },
  "devDependencies": {
    "@types/cors": "^2.8.17",
    "@types/dagre": "^0.7.52",
    "@types/express": "^4.17.21",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@types/ws": "^8.5.12",
    "@vitejs/plugin-react": "^4.3.0",
    "autoprefixer": "^10.4.20",
    "concurrently": "^9.0.0",
    "postcss": "^8.4.47",
    "tailwindcss": "^3.4.0",
    "tsx": "^4.19.0",
    "typescript": "^5.6.0",
    "vite": "^5.4.0"
  }
}
```

- [ ] **Step 2: Create vite.config.ts**

Copy from `minions-viz/vite.config.ts` and keep identical. It already handles the shared types alias and server proxy.

- [ ] **Step 3: Create tsconfig.json and tsconfig.server.json**

Copy both from `minions-viz/`. No changes needed.

- [ ] **Step 4: Create tailwind.config.js**

```js
export default {
  content: ["./index.html", "./src/web/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
};
```

- [ ] **Step 5: Create postcss.config.js**

```js
export default {
  plugins: { tailwindcss: {}, autoprefixer: {} },
};
```

- [ ] **Step 6: Create index.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>MinionsVIZ — Mission Control</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet" />
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/web/main.tsx"></script>
</body>
</html>
```

- [ ] **Step 7: Create env.d.ts and main.tsx stubs**

`src/web/env.d.ts`:
```typescript
/// <reference types="vite/client" />
```

`src/web/main.tsx`:
```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <div style={{ color: "#F1F5F9", background: "#0A0E1A", height: "100vh", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "Space Grotesk" }}>
      MinionsVIZ V2 — scaffold OK
    </div>
  </StrictMode>
);
```

- [ ] **Step 8: Install dependencies and verify build**

```bash
cd minions-viz-v2 && npm install && npx vite build
```

Expected: build succeeds with no errors.

- [ ] **Step 9: Commit**

```bash
git add minions-viz-v2/
git commit -m "feat(viz-v2): scaffold project with Vite + React + Tailwind"
```

---

### Task 2: Design System CSS

**Files:**
- Create: `minions-viz-v2/src/web/index.css`

- [ ] **Step 1: Write the complete design system CSS**

Reference: `docs/superpowers/specs/2026-04-28-minionsviz-v2/design-system.md`

The CSS must include all tokens from the spec: base surfaces, text, role colors, status colors, buffer ring colors, typography, motion tokens, elevation/shadows, and component classes (panel-card, surface-card, metric-card, data-table, toolbar, empty-state, pill, badge, limit-select, kbd, section-label, scroll-region, page-container, prose-mos).

Key structure:
```css
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  color-scheme: dark;
  /* All tokens from design-system.md spec */
}

body { /* Dark space background with subtle radial gradients */ }
/* Scrollbar, focus rings, animations, component classes */
/* prefers-reduced-motion overrides */
```

Implement every token and component class from the design-system.md spec. Use the dark space palette (`#070B14` to `#0F172A`), frosted glass panels, role-color glow shadows.

- [ ] **Step 2: Verify build**

```bash
cd minions-viz-v2 && npx vite build
```

- [ ] **Step 3: Commit**

```bash
git add minions-viz-v2/src/web/index.css
git commit -m "feat(viz-v2): add Mission Control design system tokens"
```

---

### Task 3: Shared Types + Role Identity

**Files:**
- Create: `minions-viz-v2/src/shared/types.ts`
- Create: `minions-viz-v2/src/web/utils/roleIdentity.ts`

- [ ] **Step 1: Copy shared types**

Copy `minions-viz/src/shared/types.ts` to `minions-viz-v2/src/shared/types.ts`. No modifications needed — these are the WebSocket store types (GruInfo, MosProject, AgentInfo, Task, LogEntry, etc.).

- [ ] **Step 2: Create roleIdentity.ts**

```typescript
import type { IconWeight } from "@phosphor-icons/react";

export interface RoleIdentity {
  key: string;
  label: string;
  color: string;
  colorRgb: string; // for rgba() usage
  icon: string; // Phosphor icon name
  avatarPath: string; // SVG path for canvas rendering
  orbitIndex: number; // 1-6, 0 for Gru
  baseOrbitPeriod: number; // seconds
  activeAnimation: string; // description key
}

export const ROLES: Record<string, RoleIdentity> = {
  gru:          { key: "gru",      label: "Gru",          color: "#F59E0B", colorRgb: "245,158,11",  icon: "Crown",          avatarPath: "M12 2l3 6 3-2v8l-3 2-3-2-3 2-3-2V6l3 2z", orbitIndex: 0, baseOrbitPeriod: 0,  activeAnimation: "corona-pulse" },
  noter:        { key: "noter",    label: "Noter",        color: "#06B6D4", colorRgb: "6,182,212",   icon: "Eye",            avatarPath: "M12 4C7 4 2.7 8.7 2 12c.7 3.3 5 8 10 8s9.3-4.7 10-8c-.7-3.3-5-8-10-8zm0 13a5 5 0 110-10 5 5 0 010 10z", orbitIndex: 1, baseOrbitPeriod: 12, activeAnimation: "scan-ripple" },
  coder:        { key: "coder",    label: "Coder",        color: "#10B981", colorRgb: "16,185,129",  icon: "CodeBlock",      avatarPath: "M8 5l-5 7 5 7M16 5l5 7-5 7", orbitIndex: 2, baseOrbitPeriod: 18, activeAnimation: "code-orbit" },
  experimenter: { key: "experimenter", label: "Experimenter", color: "#F97316", colorRgb: "249,115,22", icon: "Flask",      avatarPath: "M9 3h6v5l4 9H5l4-9V3z", orbitIndex: 3, baseOrbitPeriod: 24, activeAnimation: "bubble-rise" },
  writer:       { key: "writer",   label: "Writer",       color: "#A855F7", colorRgb: "168,85,247",  icon: "PenNib",         avatarPath: "M3 21l1.5-4.5L17.3 3.8a1.5 1.5 0 012.1 0l.8.8a1.5 1.5 0 010 2.1L7.5 19.5z", orbitIndex: 4, baseOrbitPeriod: 30, activeAnimation: "ink-flow" },
  reviewer:     { key: "reviewer", label: "Reviewer",     color: "#3B82F6", colorRgb: "59,130,246",  icon: "MagnifyingGlass", avatarPath: "M10 2a8 8 0 105.3 14l4.4 4.3 1.4-1.4-4.3-4.4A8 8 0 0010 2zm0 2a6 6 0 110 12 6 6 0 010-12z", orbitIndex: 5, baseOrbitPeriod: 36, activeAnimation: "sweep-scan" },
  ethics:       { key: "ethics",   label: "Ethics",       color: "#F43F5E", colorRgb: "244,63,94",   icon: "Scales",         avatarPath: "M12 2v4m0 12v4M5 12H2m20 0h-3M7.5 7.5l-2-2m13 13l-2-2M7.5 16.5l-2 2m13-13l-2 2", orbitIndex: 6, baseOrbitPeriod: 42, activeAnimation: "scale-oscillate" },
};

export function getRoleIdentity(agentId: string): RoleIdentity {
  const key = agentId.toLowerCase().replace(/[^a-z]/g, "");
  return ROLES[key] ?? { key: agentId, label: agentId, color: "#64748B", colorRgb: "100,116,139", icon: "Robot", avatarPath: "", orbitIndex: -1, baseOrbitPeriod: 20, activeAnimation: "none" };
}

export function bufferRingStyle(bufferCount: number): { thickness: number; color: string; speed: number } {
  if (bufferCount <= 0) return { thickness: 0, color: "transparent", speed: 0 };
  if (bufferCount <= 3) return { thickness: 3, color: "rgba(251,191,36,0.35)", speed: 8 };
  if (bufferCount <= 10) return { thickness: 6, color: "rgba(245,158,11,0.55)", speed: 5 };
  if (bufferCount <= 20) return { thickness: 10, color: "rgba(239,68,68,0.65)", speed: 3 };
  return { thickness: 14, color: "rgba(220,38,38,0.8)", speed: 1.5 };
}
```

- [ ] **Step 3: Commit**

```bash
git add minions-viz-v2/src/shared/ minions-viz-v2/src/web/utils/roleIdentity.ts
git commit -m "feat(viz-v2): add shared types and role identity system"
```

---

### Task 4: Data Layer

**Files:**
- Create: `minions-viz-v2/src/web/hooks/useStore.ts`
- Create: `minions-viz-v2/src/web/hooks/useLimitPref.ts`
- Create: `minions-viz-v2/src/web/hooks/useAnimationFrame.ts`
- Create: `minions-viz-v2/src/web/utils/format.ts`

- [ ] **Step 1: Copy and adapt useStore.ts**

Copy `minions-viz/src/web/hooks/useStore.ts`. Keep all existing functionality (WebSocket connection, store state, gruById, projectByPort, selectGru, selectProject). No changes to the data model.

- [ ] **Step 2: Copy useLimitPref.ts and format.ts**

Copy `minions-viz/src/web/hooks/useLimitPref.ts` and `minions-viz/src/web/utils/format.ts` unchanged.

- [ ] **Step 3: Create useAnimationFrame.ts**

```typescript
import { useRef, useEffect, useCallback } from "react";

export function useAnimationFrame(callback: (dt: number) => void, active = true) {
  const rafRef = useRef<number>(0);
  const prevRef = useRef<number>(0);
  const cbRef = useRef(callback);
  cbRef.current = callback;

  const loop = useCallback((time: number) => {
    if (prevRef.current) {
      const dt = Math.min(time - prevRef.current, 50); // cap at 50ms to avoid spiral
      cbRef.current(dt);
    }
    prevRef.current = time;
    rafRef.current = requestAnimationFrame(loop);
  }, []);

  useEffect(() => {
    if (!active) return;
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [active, loop]);
}
```

- [ ] **Step 4: Commit**

```bash
git add minions-viz-v2/src/web/hooks/ minions-viz-v2/src/web/utils/format.ts
git commit -m "feat(viz-v2): add data layer hooks and utilities"
```

---

### Task 5: Server

**Files:**
- Create: `minions-viz-v2/src/server/index.ts`
- Create: `minions-viz-v2/src/server/grus.ts`
- Create: `minions-viz-v2/src/server/mosFs.ts`
- Create: `minions-viz-v2/src/server/poller.ts`
- Create: `minions-viz-v2/src/server/projects.ts`
- Create: `minions-viz-v2/src/server/state.ts`
- Create: `minions-viz-v2/src/server/roleLog.ts`

- [ ] **Step 1: Copy all server files**

Copy all files from `minions-viz/src/server/` to `minions-viz-v2/src/server/`. These handle Gru discovery, EACN3 polling, project state, filesystem views, and WebSocket broadcasting. No modifications needed to existing files.

- [ ] **Step 2: Create roleLog.ts**

```typescript
import { Router } from "express";
import { readFile, stat } from "fs/promises";
import { watch } from "fs";
import type { WebSocket } from "ws";

const router = Router();

router.get("/api/mos/project/:port/role-log/:role", async (req, res) => {
  const { port, role } = req.params;
  const gruId = req.query.gru as string;
  const tail = parseInt(req.query.tail as string) || 500;

  if (!gruId) return res.status(400).json({ error: "gru query param required" });

  // Resolve project path from gru registry
  const { findGruRoot } = await import("./grus.js");
  const gruRoot = findGruRoot(gruId);
  if (!gruRoot) return res.status(404).json({ error: "Gru not found" });

  const logPath = `${gruRoot}/project_${port}/logs/role-${role}.log`;

  try {
    await stat(logPath);
  } catch {
    return res.status(404).json({ error: "Log file not found" });
  }

  try {
    const content = await readFile(logPath, "utf-8");
    const lines = content.split("\n");
    const tailLines = lines.slice(-tail).join("\n");
    res.type("text/plain").send(tailLines);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

export function setupRoleLogWatcher(wss: Set<WebSocket>, gruId: string, port: number, role: string, gruRoot: string) {
  const logPath = `${gruRoot}/project_${port}/logs/role-${role}.log`;
  let lastSize = 0;

  try {
    const watcher = watch(logPath, async () => {
      try {
        const s = await stat(logPath);
        if (s.size > lastSize) {
          const content = await readFile(logPath, "utf-8");
          const newContent = content.slice(lastSize);
          lastSize = s.size;
          const msg = JSON.stringify({ type: "role-log", gruId, port, role, data: newContent });
          wss.forEach((ws) => { if (ws.readyState === 1) ws.send(msg); });
        }
      } catch {}
    });
    return watcher;
  } catch {
    return null;
  }
}

export default router;
```

- [ ] **Step 3: Register roleLog router in index.ts**

Add to `src/server/index.ts` after existing route registrations:
```typescript
import roleLogRouter from "./roleLog.js";
app.use(roleLogRouter);
```

- [ ] **Step 4: Commit**

```bash
git add minions-viz-v2/src/server/
git commit -m "feat(viz-v2): add server with role-log streaming endpoint"
```
