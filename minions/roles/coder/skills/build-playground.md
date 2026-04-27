# Skill — Build Playground

Create a self-contained interactive HTML explorer when visual configuration is
hard to express in text.

## Core move

Build a local playground with controls, a live preview, and a generated prompt or
configuration output. Use this for exploration and communication, not as a
substitute for production dashboard work.

## Procedure

1. **Confirm the exploration target.** Identify the visual or structural choice
   the user or role needs to tune: layout, chart encoding, prompt structure,
   parameter grid, concept map, or document critique workflow.
2. **Choose a lightweight output path.** Prefer
   `workspace/playgrounds/<slug>.html` for project-local prototypes. For paper
   figures, coordinate with Writer and use `workspace/paper/figures/prototypes/`.
3. **Make it self-contained.** Use one HTML file with embedded CSS and JS unless
   the project already has a stronger local pattern.
4. **Expose real controls.** Include sliders, selects, checkboxes, tabs, or text
   inputs for the dimensions users are likely to vary. Avoid explanatory filler.
5. **Show live output.** The preview should update immediately and the generated
   prompt/config should be copyable or easy to inspect.
6. **Keep production boundaries clear.** If the prototype should become part of
   `minions-viz` or another app, hand off a separate implementation plan after
   the playground proves the interaction.

## When to invoke

- A role needs to explore figure layouts, dashboard states, prompt parameters, or
  experiment configuration spaces interactively.
- The request mentions a playground, explorer, visual tool, prompt builder, or
  live preview.
- Static prose would leave too many visual degrees of freedom ambiguous.

## Pitfalls

- Building a marketing page instead of the usable control surface.
- Treating a prototype as reviewed production UI.
- Hiding important state behind decorative visuals.
- Writing outside Coder-owned workspace paths without an explicit handoff.

## Output habit

Return the playground path, the main controls implemented, and any assumptions
that must be resolved before productionizing it.
