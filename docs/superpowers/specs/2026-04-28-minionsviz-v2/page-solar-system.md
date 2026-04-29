# Page: Solar System (EACN Network Topology)

Default homepage. A 2.5D solar system where Gru is the central star and Roles are orbiting planets.

## Rendering Architecture

Two-layer composite:
1. **Canvas layer** (bottom): background stars, orbital path ellipses, particle effects, comet trails, message light beams, star dust, buffer ring animations
2. **HTML overlay** (top): planet node divs (positioned absolutely), labels, tooltips, slide-out detail panel

Canvas runs at 60fps via `requestAnimationFrame`. HTML nodes are positioned via CSS `transform: translate()` synced to canvas coordinates each frame.

## 2.5D Perspective

The solar system is viewed from ~30° above the orbital plane.

- Orbital paths are ellipses: `radiusX` is the full orbit size, `radiusY = radiusX * 0.4`
- Each planet has a parametric position: `x = cx + rx * cos(θ)`, `y = cy + ry * sin(θ)`
- **Z-simulation**: when `sin(θ) < 0` (back half of orbit), the planet is "behind" the star:
  - Scale down to 0.75
  - Reduce opacity to 0.6
  - Render below star z-index
- When `sin(θ) > 0` (front half), planet is "in front":
  - Scale up to 1.0 (or 1.05 on hover)
  - Full opacity
  - Render above star z-index
- Smooth interpolation between front/back states (no sudden flip)

## Star (Gru)

- Center of canvas
- Size: ~80px diameter (largest node)
- Golden corona effect: multiple concentric glow rings with slow pulse
- Crown avatar SVG rendered inside
- Label: project name + "GRU" below
- When Gru is active: corona expands, pulse speeds up
- When Gru is idle: corona contracts, slow breathing

## Planets (Roles)

Each role occupies a fixed orbital ring at increasing radii from the star:

| Ring | Role | Radius (relative) | Orbit Period (base) |
|------|------|--------------------|---------------------|
| 1 | Noter | 0.25 | 12s |
| 2 | Coder | 0.38 | 18s |
| 3 | Experimenter | 0.50 | 24s |
| 4 | Writer | 0.62 | 30s |
| 5 | Reviewer | 0.74 | 36s |
| 6 | Ethics | 0.86 | 42s |

Radii are relative to the available canvas size. Actual pixel values computed on mount and resize.

Planet node size: ~48px diameter. Contains the role avatar SVG + role-color glow ring.

### Planet States

| State | Visual | Orbit | Glow |
|-------|--------|-------|------|
| active | Full color, avatar visible | Moving (speed reflects activity) | Full role-color glow |
| sleeping | 40% opacity, dimmed | Near-static (very slow drift) | Faint glow |
| dismissed | Ghost outline only, 20% opacity | Stopped | No glow |
| spawning (transition) | scale 0→1.1→1 over 600ms | Accelerates from 0 over 800ms | Glow fades in |
| dismissing (transition) | Flash → fade to ghost over 800ms | Decelerates to stop over 800ms | Glow fades out |

### Orbit Speed Modulation

Base period is listed above. Actual speed is modulated:
- `active` + high recent message count → speed × 1.5
- `active` + low activity → speed × 1.0
- `sleeping` → speed × 0.05 (barely drifting)
- All speed changes apply gradually via `--ease-inertia` over 800ms

## Buffer Rings (Saturn-style)

Each planet (and the star) can display a buffer ring — a rotating elliptical band around the node, tilted to match the 2.5D perspective.

Rendered on the Canvas layer, behind the HTML planet node but in front of the orbital path.

| Buffer Count | Ring Thickness | Color | Rotation Speed |
|--------------|---------------|-------|----------------|
| 0 | invisible | — | — |
| 1-3 | 3px | `rgba(251,191,36,0.35)` amber | 8s per revolution |
| 4-10 | 6px | `rgba(245,158,11,0.55)` orange | 5s per revolution |
| 11-20 | 10px | `rgba(239,68,68,0.65)` red | 3s per revolution |
| 20+ | 14px | `rgba(220,38,38,0.8)` deep red + pulse | 1.5s per revolution |

Ring is an ellipse slightly larger than the planet node, tilted ~20° from the orbital plane. Ring rotation is independent of orbital motion. Ring thickness and color transitions are animated (gradual change when buffer count updates).

## Orbital Paths

Drawn on Canvas as faint ellipses:
- Stroke: `rgba(255,255,255,0.06)` default
- Stroke on hover (when mouse near): `rgba(role-color, 0.2)`
- Dashed pattern: `[4, 8]` for sleeping roles, solid for active

## Message Beams

When a message is sent between agents, a light beam travels from sender to receiver along a curved path (quadratic bezier, arcing above the orbital plane).

- Color: sender's role color
- Duration: 800ms
- Trail: fading tail behind the beam head
- On arrival: brief flash at receiver node

Multiple concurrent messages are supported. Old beams fade out over 400ms after arrival.

## Background

- Static star field: ~200 small dots at random positions, varying brightness (0.3-0.8 opacity), subtle twinkle
- Mouse parallax: star field shifts slightly opposite to mouse movement (2-4px max offset), creating depth
- Subtle radial gradient from center (warm, very faint golden tint from the Gru star)

## Mouse Interactions

| Action | Effect |
|--------|--------|
| Mouse near planet (<80px) | Planet glow intensifies, emits 3-5 micro particles, label becomes fully opaque |
| Hover planet | Orbit pauses smoothly (deceleration), tooltip appears with: role name, state, buffer count, last activity time |
| Click planet | Right slide-out panel opens with role detail (see Shared Components) |
| Hover orbital path | Path brightens to role color at 20% opacity |
| Drag planet | Planet follows mouse, detached from orbit. Elastic rubber-band line to orbital position. Release → spring back with `--ease-spring` |
| Mouse in empty space | Faint star-dust trail follows cursor (5-8 tiny particles, fade over 400ms) |
| Scroll wheel | Zoom in/out (0.5x to 2.0x). Zoom toward cursor position. Smooth transition. |
| Mouse leave canvas | All hover effects fade out over 300ms |

No double-click interactions.

## Data Sources

- Agents list + state: from WebSocket store (`store.agents`)
- Buffer counts: from EACN3 agent info (buffered event count per agent)
- Messages: from WebSocket store (`store.messages`) — used for message beam animations
- Tasks: from WebSocket store (`store.tasks`) — shown as small markers on orbital paths
- Project metadata: from WebSocket store for project name, status

## Responsive Behavior

- Canvas resizes to fill available space (below top bar, above dock)
- Orbital radii recalculate on resize
- Below 768px width: labels hidden by default (show on hover only), planet sizes reduced to 36px
- Zoom level persisted in localStorage
