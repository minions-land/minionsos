---
slug: build-playground
summary: Build a self-contained interactive HTML explorer (controls + live preview + generated config) when visual configuration is hard to express in text.
layer: logical
tools:
version: 3
status: active
supersedes:
references:
provenance: human
---

# Skill — Build Playground

A self-contained HTML explorer for visual or structural choices that prose cannot pin down.

## When to invoke

- A role needs to explore figure layouts, dashboard states, prompt parameters, or experiment configuration spaces interactively.
- The request mentions a playground, explorer, visual tool, prompt builder, or live preview.
- Static prose would leave too many visual degrees of freedom ambiguous.

Use this for exploration and communication, not as a substitute for production dashboard work.

## Structure

One HTML file with embedded CSS and JS. Three surfaces: real controls (sliders, selects, checkboxes, tabs, text inputs), a live preview that updates immediately, and a copyable generated prompt or configuration. No marketing copy, no decorative visuals that hide state. Production handoff happens after the prototype proves the interaction.

## Procedure

1. **Confirm the exploration target.** Identify the visual or structural choice the user or role needs to tune: layout, chart encoding, prompt structure, parameter grid, concept map, or document critique workflow.
2. **Choose a lightweight output path.** Prefer `branches/<expert>/playgrounds/<slug>.html` for project-local prototypes. For paper figures, coordinate with Expert and use `branches/<expert>/paper/figures/prototypes/`.
3. **Make it self-contained.** One HTML file with embedded CSS and JS unless the project already has a stronger local pattern. If writing code, apply SYSTEM.md §4 Stage 1 code quality gate.
4. **Expose real controls** for the dimensions users are likely to vary. Avoid explanatory filler.
5. **Show live output.** Preview updates immediately; generated prompt or config is copyable or easy to inspect.
6. **Keep production boundaries clear.** If the prototype should become part of `minions-viz` or another app, hand off a separate implementation plan after the playground proves the interaction.
7. **Report** the playground path, the main controls implemented, and any assumptions that must be resolved before productionizing it.

## Pitfalls

- Building a marketing page instead of the usable control surface.
- Treating a prototype as reviewed production UI.
- Hiding important state behind decorative visuals.
- Writing outside Expert-owned workspace paths without an explicit handoff.
