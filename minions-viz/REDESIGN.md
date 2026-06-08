# MinionsVIZ Redesign — Marvis-Inspired Polish

**Date:** 2026-05-22  
**Reference:** Tencent Marvis APP frontend design (macOS HIG + Material Design fusion)

## Design Philosophy

MinionsVIZ is an Observatory dashboard, not a chat interface. The redesign lifts Marvis's **visual language** — macOS-inspired softness, frosted glass, refined accent system, rounded surfaces, layered depth — and applies it to the existing Observatory structure (3D scene, agent roster, task board, terminals, events, Draft/Book/Atlas views).

## Key Improvements

### 1. **Refined Color System**

**Before:** Hardcoded `#00d4ff` scattered across Library/Atlas views, inconsistent opacity values  
**After:** Unified design token system

```css
--accent: #22d3ee;
--accent-hover: #06b6d4;
--accent-soft: rgba(34, 211, 238, 0.12);
--accent-glow: rgba(34, 211, 238, 0.25);
```

All components now use `var(--accent)` instead of hardcoded cyan. Role colors get matching `-soft` variants for backgrounds.

### 2. **Elevated Surfaces**

**Backdrop blur:** `blur(14px)` → `saturate(180%) blur(20px)` (Marvis uses saturation boost for richer glass)  
**Shadows:** Layered depth system with 4 tiers:

```css
--shadow-sm: 0 2px 8px rgba(0,0,0,.12), 0 1px 2px rgba(0,0,0,.24);
--shadow: 0 8px 24px rgba(0,0,0,.24), 0 2px 6px rgba(0,0,0,.32);
--shadow-lg: 0 20px 60px rgba(0,0,0,.4), 0 4px 12px rgba(0,0,0,.5);
--shadow-xl: 0 30px 80px rgba(0,0,0,.5), 0 8px 20px rgba(0,0,0,.6);
```

**Inset highlights:** `0 0 0 1px rgba(255,255,255,.04) inset` on panels for subtle rim lighting

### 3. **Smoother Interactions**

- **Hover states:** `translateY(-2px)` with shadow elevation (was `-1px`)
- **Transitions:** 140ms → 180-200ms with `var(--ease-out)` cubic-bezier
- **Focus rings:** Unified `var(--accent)` with 3px soft glow (`--accent-soft`)
- **Active tabs:** Top accent line via `::before` pseudo-element
- **Animations:** Entry animations for panels (`@keyframes panel-in`, `dropdown-in`, `picker-in`)

### 4. **Typography Hierarchy**

- **Letter-spacing:** Tightened from `.08em` to `.06em` for body mono, kept `.12em` for uppercase labels
- **Weight distribution:** Added `font-weight: 600` to active states and section headers
- **Gradient text:** Brand and picker titles use `background-clip: text` gradient

### 5. **Component Polish**

#### Topbar & Bottom Dock
- Height: 54px → 56px / 58px → 62px (more breathing room)
- Chips: 28px → 30px height, refined shadow with inset highlight
- Primary button: Gradient with stronger glow on hover
- Brand dot: Added `::after` pseudo for inner depth

#### Picker
- Card width: 760px → 820px
- Padding: 30px → 36px
- Item hover: `-1px` → `-2px` translateY, stronger shadow
- Entry animation: `@keyframes picker-in` with scale + translateY

#### Agent Roster
- Row hover: Added `translateX(2px)` slide + border
- Active state: Accent glow shadow
- Swatch size: 10px → 11px with stronger glow

#### Task Board
- Column backdrop: Added `saturate(180%)`
- Card hover: `-1px` → `-2px` translateY
- Tags: Added subtle border (`--line-soft`)

#### Metric HUD
- Bar width: 3px → 4px with stronger glow
- Card hover: `translateY(-2px)` elevation

#### Library & Atlas Views
- **Fixed:** All hardcoded `#00d4ff` → `var(--accent)`
- **Fixed:** All `rgba(255,255,255,...)` → design tokens
- Search/filter inputs: Refined focus states with accent glow
- Detail panels: Slide-in animation, stronger backdrop
- Empty states: Larger icons (48px → 56px) with drop-shadow

#### Badges
- Added border + shadow for depth
- Padding: 2px 8px → 3px 9px

#### Scrollbars
- Width: 8px → 10px
- Thumb: `rgba(255,255,255,.09)` → `.12` with 2px transparent border (padding-box clip)

### 6. **Micro-Animations**

- **Brand dot:** Pulsing glow animation
- **Read-only chip dot:** `@keyframes pulse-dot` (2s ease-in-out)
- **Spinner:** `@keyframes pulse` for loading states
- **Dropdown:** Scale + translateY entrance
- **Panel slide:** Library detail panel slides in from right

## Files Changed

- `minions-viz/src/web/index.css` — Complete redesign (419 lines → 980 lines with expanded Library/Atlas)

## Visual Comparison

**Before:**
- Flat surfaces with minimal depth
- Inconsistent hover states
- Hardcoded colors in Library/Atlas
- Basic focus rings
- No entry animations

**After:**
- Layered glass morphism with saturation boost
- Unified hover elevation system
- Token-based accent system throughout
- Refined focus states with soft glow
- Smooth entry/exit animations
- Stronger visual hierarchy

## Design Tokens Reference

```css
/* Depth layers */
--bg-void: #03040a
--bg-space: #060914
--bg-nebula: #0a1020
--panel-bg: rgba(10, 15, 28, 0.82)      /* was 0.74 */
--panel-strong: rgba(10, 15, 28, 0.95)  /* was 0.92 */
--surface: rgba(24, 34, 58, 0.65)       /* was 0.55 */
--surface-hi: rgba(38, 52, 86, 0.85)    /* was 0.75 */
--surface-hover: rgba(48, 62, 96, 0.75) /* new */

/* Borders */
--line: rgba(255, 255, 255, 0.08)
--line-hi: rgba(255, 255, 255, 0.18)    /* was 0.2 */
--line-soft: rgba(255, 255, 255, 0.04)  /* was 0.035 */
--line-focus: rgba(34, 211, 238, 0.5)   /* new */

/* Typography */
--text: #eef2ff
--text-2: #c5cfe4
--text-3: #9ca8c2                       /* new */
--muted: #6a7a96
--muted-2: rgba(106, 122, 150, 0.55)

/* Accent system (replaces hardcoded #00d4ff) */
--accent: #22d3ee
--accent-hover: #06b6d4
--accent-soft: rgba(34, 211, 238, 0.12)
--accent-glow: rgba(34, 211, 238, 0.25)

/* Role colors with soft variants */
--role-gru: #f59e0b
--role-gru-soft: rgba(245, 158, 11, 0.15)
--role-observatory: #22d3ee
--role-observatory-soft: rgba(34, 211, 238, 0.15)
/* ... (all roles get -soft variants) */

/* Radius (Marvis uses larger corners) */
--radius-xl: 18px                       /* new */
--radius: 14px
--radius-sm: 10px
--radius-xs: 6px
--radius-pill: 9999px

/* Animation */
--ease-out: cubic-bezier(0.16, 1, 0.3, 1)
--ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1)  /* new */
```

## Build Verification

```bash
cd minions-viz && npm run build
# ✓ built in 2.02s
# CSS: 37.21 kB │ gzip: 7.09 kB
```

## Next Steps (Optional)

1. **D3 graph visualizations** — Draft/Library/Atlas canvas placeholders ready for force-directed layouts
2. **VR polish** — Apply same design tokens to WebXR overlay UI
3. **Dark/light toggle** — Foundation in place with `color-scheme: dark`
4. **Responsive breakpoints** — Current design optimized for 1440px+

---

**Result:** MinionsVIZ now has the refined, polished feel of Marvis while preserving its unique Observatory identity. Every surface, interaction, and transition has been elevated to match modern macOS design standards.
