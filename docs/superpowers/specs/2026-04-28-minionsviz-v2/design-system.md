# Design System

## Color Tokens

### Base Surfaces
| Token | Value | Usage |
|-------|-------|-------|
| `--bg-void` | `#070B14` | Deepest background (solar system canvas) |
| `--bg-space` | `#0A0E1A` | Primary page background |
| `--bg-nebula` | `#0F172A` | Elevated surfaces |
| `--panel-bg` | `rgba(15,23,42,0.85)` | Frosted glass panels |
| `--panel-hover` | `rgba(15,23,42,0.95)` | Panel hover state |
| `--surface` | `rgba(30,41,59,0.7)` | Cards, inputs |
| `--line` | `rgba(255,255,255,0.08)` | Borders |
| `--line-glow` | `rgba(255,255,255,0.15)` | Active borders |

### Text
| Token | Value |
|-------|-------|
| `--text` | `#F1F5F9` |
| `--text-2` | `#CBD5E1` |
| `--muted` | `#64748B` |
| `--muted-2` | `rgba(100,116,139,0.6)` |

### Role Colors (signature neon)
| Role | Token | Hex | Avatar | Micro-animation (active) |
|------|-------|-----|--------|--------------------------|
| Gru | `--role-gru` | `#F59E0B` | Crown/star | Golden pulse + corona expansion |
| Noter | `--role-noter` | `#06B6D4` | Lens/eye | Scanning wave ripple |
| Coder | `--role-coder` | `#10B981` | Brackets `</>` | Code characters orbiting |
| Experimenter | `--role-exp` | `#F97316` | Flask/beaker | Bubbling particles rising |
| Writer | `--role-writer` | `#A855F7` | Quill/feather | Ink flow trail |
| Reviewer | `--role-reviewer` | `#3B82F6` | Magnifying glass | Sweep scan line |
| Ethics | `--role-ethics` | `#F43F5E` | Balance/shield | Scale gentle oscillation |

### Status Colors
| Token | Value | Usage |
|-------|-------|-------|
| `--status-active` | Role's own color | Active agent |
| `--status-sleeping` | Role color at 30% opacity | Sleeping agent |
| `--status-dismissed` | `#334155` | Ghost outline only |
| `--status-completed` | `#10B981` | Completed tasks |
| `--status-bidding` | `#3B82F6` | Bidding tasks |
| `--status-unclaimed` | `#F59E0B` | Unclaimed tasks |
| `--status-error` | `#EF4444` | Errors |

### Buffer Ring Colors
Buffer count maps to a gradient from transparent → amber → deep red:
- 0 buffer: no ring visible
- 1-3: `rgba(251,191,36,0.3)` thin ring, slow rotation
- 4-10: `rgba(245,158,11,0.5)` medium ring, moderate rotation
- 11-20: `rgba(239,68,68,0.6)` thick ring, fast rotation
- 20+: `rgba(220,38,38,0.8)` very thick ring, rapid rotation + pulse

## Typography

| Token | Font | Usage |
|-------|------|-------|
| `--font-display` | Space Grotesk 700 | Page titles, hero text |
| `--font-heading` | Space Grotesk 600 | Section headers |
| `--font-body` | Space Grotesk 400 | Body text |
| `--font-mono` | JetBrains Mono 400 | Data, code, terminal, labels |
| `--font-mono-bold` | JetBrains Mono 600 | Emphasized data |

Google Fonts import:
```
Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600
```

## Motion Tokens

All transitions use easing curves — never linear, never instant.

| Token | Value | Usage |
|-------|-------|-------|
| `--ease-out` | `cubic-bezier(0.16, 1, 0.3, 1)` | Most UI transitions |
| `--ease-spring` | `cubic-bezier(0.34, 1.56, 0.64, 1)` | Bouncy interactions (drag release) |
| `--ease-inertia` | `cubic-bezier(0.25, 0.46, 0.45, 0.94)` | Orbital start/stop |
| `--duration-fast` | `200ms` | Hover, focus |
| `--duration-normal` | `350ms` | Panel open/close |
| `--duration-slow` | `600ms` | Page transitions |
| `--duration-orbit` | `800ms` | Orbital acceleration/deceleration |

### Inertia Rules
- Planet orbit start: accelerate over 800ms with `--ease-inertia`
- Planet orbit stop: decelerate over 800ms, coast to a halt
- Panel slide-in: 350ms `--ease-out`
- Panel slide-out: 250ms ease-in
- Element appear: fade-in 300ms + translateY(12px→0)
- Element disappear: fade-out 200ms + translateY(0→8px)
- Page transition: crossfade 400ms
- Toast: slide-up 300ms, auto-dismiss fade-out 200ms
- Node creation (new role spawned): scale(0)→scale(1.1)→scale(1) over 600ms spring
- Node removal (role dismissed): glow flash → fade to ghost outline over 800ms

### prefers-reduced-motion
All animations collapse to opacity-only transitions at 200ms. Orbital motion stops. Particles disabled. Buffer rings static.

## Elevation / Shadows

| Token | Value |
|-------|-------|
| `--shadow-glow-sm` | `0 0 8px rgba(role-color, 0.3)` |
| `--shadow-glow` | `0 0 20px rgba(role-color, 0.4)` |
| `--shadow-glow-lg` | `0 0 40px rgba(role-color, 0.3), 0 0 80px rgba(role-color, 0.15)` |
| `--shadow-panel` | `0 8px 32px rgba(0,0,0,0.5)` |

## Backdrop Blur
Panels use `backdrop-filter: blur(16px)` for frosted glass effect on dark surfaces.
