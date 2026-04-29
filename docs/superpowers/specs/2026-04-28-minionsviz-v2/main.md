# MinionsVIZ V2 — Design Spec

## Overview

Full redesign of the MinionsVIZ Observatory dashboard. Dark "Mission Control" aesthetic with playful role personalities. The hero view is a 2.5D solar system representing the EACN network topology.

New frontend lives in a **separate folder** (`minions-viz-v2/`), does not modify `minions-viz/`. Reuses the same Express/WebSocket server backend with minimal extensions.

## Goals

- Go-viral visual impact: the solar system view should be screenshot-worthy
- Functional depth: all current MinionsVIZ data remains accessible
- Playful identity: each Role is a distinct "character" with color, avatar, animation
- Fluid motion: every state change is gradual, with inertia and easing — nothing appears or disappears instantly

## Constraints

- Read-only: never POST/PUT/DELETE to EACN3
- Never call `/api/events/{agent_id}` (drains real queues)
- Only modify files under `minions-viz-v2/`
- Must work with existing `~/.minionsos/` registry and Gru discovery

## Three Pages

| Page | Purpose | Entry |
|------|---------|-------|
| **Solar System** | 2.5D EACN network topology — hero/default | Homepage |
| **EACN Dashboard** | Tasks (board + tree), agents, messages, event log | Dock icon |
| **Terminal Hub** | Read-only terminals for all agents | Dock icon |

Navigation: bottom dock bar with glowing icons, current page highlighted in theme color.

## Tech Stack

- React 18 + Vite 5 + TypeScript
- Tailwind CSS 3 (dark theme tokens)
- HTML5 Canvas (solar system effects layer) + HTML/CSS overlay (interactive nodes)
- xterm.js (terminal rendering)
- @xyflow/react retained for Task Tree
- Express + WebSocket server (extended from current viz server)
- Fonts: Space Grotesk (headings), JetBrains Mono (data/terminal)

## Section Specs

- [Design System](./design-system.md)
- [Page: Solar System](./page-solar-system.md)
- [Page: EACN Dashboard](./page-dashboard.md)
- [Page: Terminal Hub](./page-terminal-hub.md)
- [Shared Components](./shared-components.md)
