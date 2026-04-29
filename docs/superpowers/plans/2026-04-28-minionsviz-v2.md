# MinionsVIZ V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new MinionsVIZ V2 frontend in `minions-viz-v2/` with a 2.5D solar system EACN topology hero view, dark Mission Control theme, and playful role personalities.

**Architecture:** Two-layer rendering (Canvas for effects + HTML overlay for interactive nodes) on a React/Vite/Tailwind stack. Reuses the existing viz Express/WebSocket server with a new role-log streaming endpoint. Three pages: Solar System (hero), EACN Dashboard, Terminal Hub.

**Tech Stack:** React 18, Vite 5, TypeScript, Tailwind CSS 3, HTML5 Canvas, xterm.js, @xyflow/react, Express, WebSocket, Space Grotesk + JetBrains Mono fonts, Phosphor Icons.

**Spec:** `docs/superpowers/specs/2026-04-28-minionsviz-v2/`

---

## File Structure

```
minions-viz-v2/
├── package.json
├── tsconfig.json
├── tsconfig.server.json
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
├── index.html
├── src/
│   ├── shared/
│   │   └── types.ts
│   ├── server/
│   │   ├── index.ts
│   │   ├── grus.ts
│   │   ├── mosFs.ts
│   │   ├── poller.ts
│   │   ├── projects.ts
│   │   ├── state.ts
│   │   └── roleLog.ts              # NEW
│   └── web/
│       ├── main.tsx
│       ├── App.tsx
│       ├── index.css
│       ├── hooks/
│       │   ├── useStore.ts
│       │   ├── useLimitPref.ts
│       │   └── useAnimationFrame.ts # NEW
│       ├── utils/
│       │   ├── format.ts
│       │   ├── roleIdentity.ts      # NEW
│       │   └── canvasUtils.ts       # NEW
│       ├── components/
│       │   ├── TopBar.tsx
│       │   ├── BottomDock.tsx
│       │   ├── GruPicker.tsx
│       │   ├── ProjectPicker.tsx
│       │   ├── SlideOutPanel.tsx
│       │   ├── TaskDetailModal.tsx
│       │   ├── GlobalSearch.tsx
│       │   ├── ToastContainer.tsx
│       │   └── EmptyState.tsx
│       ├── pages/
│       │   ├── solar-system/
│       │   │   ├── SolarSystemPage.tsx
│       │   │   ├── SolarSystemCanvas.tsx
│       │   │   ├── PlanetNode.tsx
│       │   │   ├── StarNode.tsx
│       │   │   └── useOrbitalEngine.ts
│       │   ├── dashboard/
│       │   │   ├── DashboardPage.tsx
│       │   │   ├── MetricBar.tsx
│       │   │   ├── AgentsPanel.tsx
│       │   │   ├── TasksPanel.tsx
│       │   │   ├── TaskTree.tsx
│       │   │   └── MessagesPanel.tsx
│       │   └── terminal/
│       │       ├── TerminalPage.tsx
│       │       ├── RoleSidebar.tsx
│       │       └── TerminalViewport.tsx
│       └── env.d.ts
```

## Task Dependency Graph

```
Task 1 (Scaffold) ──► Task 2 (Design System) ──► Task 6 (Shared Components)
       │                      │                          │
       ├──► Task 3 (Types) ──►├──► Task 4 (Data Layer) ──►├──► Task 7+8 (Solar System)
       │                      │                          │
       └──► Task 5 (Server) ──┘                          ├──► Task 9 (Dashboard)
                                                         ├──► Task 10 (Terminal)
                                                         └──► Task 11 (App Assembly)
                                                                    │
                                                              Task 12 (Build+Test)
```

Parallelizable groups after Task 1:
- Group A: Task 2 + Task 3 + Task 5 (all independent after scaffold)
- Group B: Task 4 + Task 6 (after Group A)
- Group C: Task 7+8, Task 9, Task 10 (after Group B, all independent)
- Group D: Task 11, Task 12 (sequential, after Group C)

## Task Summary

| Task | Name | Est. | Depends On |
|------|------|------|------------|
| 1 | Project Scaffolding | 5 min | — |
| 2 | Design System CSS | 10 min | 1 |
| 3 | Shared Types + Role Identity | 8 min | 1 |
| 4 | Data Layer (hooks + utils) | 10 min | 1, 3 |
| 5 | Server (copy + extend) | 10 min | 1, 3 |
| 6 | Shared Components | 20 min | 2, 4 |
| 7 | Solar System Canvas Engine | 25 min | 2, 3, 4 |
| 8 | Solar System HTML + Page | 15 min | 6, 7 |
| 9 | Dashboard Page | 20 min | 4, 6 |
| 10 | Terminal Hub Page | 15 min | 4, 5, 6 |
| 11 | App Assembly + Routing | 10 min | 8, 9, 10 |
| 12 | Build Verification | 5 min | 11 |

Detailed task specs are in phase files:
- [Phase 1: Foundation](./2026-04-28-minionsviz-v2-phase1.md) — Tasks 1-5
- [Phase 2: Components + Solar System](./2026-04-28-minionsviz-v2-phase2.md) — Tasks 6-8
- [Phase 3: Dashboard + Terminal + Assembly](./2026-04-28-minionsviz-v2-phase3.md) — Tasks 9-12
