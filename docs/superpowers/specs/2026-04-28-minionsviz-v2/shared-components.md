# Shared Components

## Bottom Dock

Fixed bottom navigation bar. The primary way to switch between the three pages.

```
┌─────────────────────────────────────────────────────┐
│   ◉ Solar System    ◉ Dashboard    ◉ Terminal Hub   │
└─────────────────────────────────────────────────────┘
```

- Height: 56px
- Background: `rgba(10,14,26,0.92)` + `backdrop-filter: blur(20px)`
- Top border: 1px solid `var(--line)`
- Three icon buttons, evenly spaced
- Each button: icon (24px) + label (10px mono) below
- Active page: icon glows in theme accent color (`--role-gru` gold by default), label fully opaque
- Inactive: icon and label at 40% opacity
- Hover: icon brightens to 70%, subtle glow
- Transition between states: 200ms ease-out
- Page switch animation: active indicator slides horizontally (not jumps) between icons

### Dock Icons
| Page | Icon concept |
|------|-------------|
| Solar System | Orbital rings / planet icon |
| Dashboard | Grid/chart icon |
| Terminal Hub | Terminal/console icon |

Use Phosphor icons (`@phosphor-icons/react`) as primary icon library.

## Top Bar

Minimal top bar, always visible.

- Height: 48px
- Background: `rgba(10,14,26,0.88)` + `backdrop-filter: blur(16px)`
- Bottom border: 1px solid `var(--line)`

Contents (left to right):
1. **MinionsOS logo** — small text "MinionsVIZ" in Space Grotesk 600, with a subtle glow
2. **Gru selector** — dropdown pill showing current Gru label. Click → dropdown list of registered Grus. Live Grus have green dot, stale ones dimmed.
3. **Project selector** — dropdown pill showing current project name + port. Click → dropdown list of projects for selected Gru. Status badge (active/dormant/closed) on each.
4. **Spacer**
5. **Connection indicator** — green dot + "CONNECTED" or red dot + "DISCONNECTED" (mono 10px)
6. **Search** — `Cmd+K` shortcut hint. Opens global search modal.
7. **Export** — snapshot download button (JSON dump)

Selectors animate open with slide-down 250ms + fade-in. Selecting a different Gru/project triggers a page-level crossfade transition.

## Gru Picker (full page)

Shown when no Gru is selected. Full-page dark view with centered card grid.

- Each Gru card: frosted glass surface, Gru label, root path (mono), live/stale indicator
- Live Grus: gold border glow, "LIVE" badge
- Stale Grus: dimmed, 60% opacity
- Cards appear with staggered fade-in (80ms delay each)
- Click → selects Gru, transitions to Project Picker

## Project Picker (full page)

Shown when Gru is selected but no project. Full-page with project card grid.

- Each project card: frosted glass, project name, port (mono), status badge, venue, role count, branch, created date
- Active projects: role-colored left border accent
- Dormant: amber tint
- Closed: dimmed, grouped separately at bottom
- Cards appear with staggered fade-in
- Click → selects project, transitions to Solar System page

## Project Unavailable State

When `selectedPort` is set but project is no longer in the Gru's project list (closed/removed):

- Centered card with warning icon
- "Project unavailable" heading
- "project_{port} is closed or no longer registered with this Gru."
- "← Back to projects" button → clears selectedPort
- Fade-in 300ms on appear

## Slide-Out Detail Panel

Right-side panel that opens when clicking a planet node (Solar System) or agent card (Dashboard).

- Width: 420px (or 90vw on mobile)
- Background: `var(--panel-bg)` + backdrop blur
- Left border: 2px solid role-color
- Slide in from right: 350ms `--ease-out`
- Slide out: 250ms ease-in
- Close: click X button, click outside panel, or press Escape

### Panel Content (Role Detail)

| Section | Content |
|---------|---------|
| Header | Role avatar (48px) + name + state badge + buffer count |
| Activity | Last 5 EACN messages involving this role (newest first) |
| Tasks | Tasks initiated by or assigned to this role (newest first, limit 10) |
| Scratchpad | Preview of `memory/{role}.md` content (first 500 chars, expandable) |
| Terminal | "Open in Terminal Hub →" link button |
| Meta | Agent ID, registration time, last heartbeat |

Each section separated by subtle divider line. Sections animate in with staggered slide-up (50ms delay).

## Task Detail Modal

Centered modal that opens when clicking a task card or task tree node.

- Max width: 560px
- Background: `var(--panel-bg)` + backdrop blur
- Scrim: `rgba(0,0,0,0.6)` behind modal
- Appear: scale(0.95)→scale(1) + fade-in 250ms
- Dismiss: fade-out 200ms. Click scrim, X button, or Escape.

### Modal Content

| Field | Display |
|-------|---------|
| Task ID | Full ID, mono font |
| Status | Colored badge |
| Initiator | Avatar + name |
| Assigned | Avatar + name (if claimed) |
| Domains | Tag pills |
| Description | Full text, prose-styled |
| Subtasks | List with status indicators (if any) |
| Results | If completed, show result summary |
| Timeline | Created → Bid → Claimed → Completed timestamps |

## Global Search Modal

`Cmd+K` to open. Centered modal with search input.

- Input: full-width, mono font, auto-focus
- Results grouped: Agents, Tasks, Messages
- Each result: icon + title + subtitle preview
- Keyboard navigation: arrow keys + Enter to select
- Select agent → opens slide-out panel
- Select task → opens task detail modal
- Appear/dismiss: same as task detail modal

## Toast Notifications

Bottom-right corner, stacked.

- Types: info (blue), success (green), error (red)
- Appear: slide-up 300ms from bottom
- Auto-dismiss: fade-out after 4s
- Max 3 visible at once, oldest dismissed first
- Frosted glass background matching panel style

## Empty States

Consistent pattern across all panels:
- Centered vertically in parent
- Icon (muted, 40px) + message text (muted, 12px)
- Fade-in 300ms on appear
- Icon uses Phosphor icon appropriate to context
