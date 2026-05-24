# 10 — Visual render

> **L2 card.** Rendering tools available to every EACN role except Noter (Noter doesn't author visuals).
> Top three: `mos_visual_render` (LaTeX/HTML/MD → image), `mos_visual_inspect` (vision-model report), `mos_visual_check` (one-shot verdict).
> Output persists under `branches/<role>/visual-reports/`.

---

## mos_visual_render

```python
args:
  source: str               # raw LaTeX, HTML, or Markdown
  format: "latex" | "html" | "md"
  out_subpath: str          # relative path under branches/<role>/visual-reports/
  page: int | None          # for multi-page LaTeX
  width_px: int | None
returns: { image_path, ms_elapsed }
```

**Use cases:** preview a Writer figure, sanity-check a TikZ diagram, render an HTML mockup before committing it.

**Pitfalls.**
- LaTeX with `\input{}` won't resolve external files unless they live in the role's branch — pass full self-contained source.
- For long Chinese / multi-section LaTeX (the Tier-0 trigger from `CLAUDE.md`), seed a `.tex` file with `reliable-file-io` first, then render via path-based render — NOT by passing the whole source string into one tool call.

---

## mos_visual_inspect

```python
args:
  image_path: str
  question: str | None       # e.g. "is the y-axis monotone? does the legend overlap?"
returns: { description, issues, ok: bool }
```

Runs a vision model over the image. Use for accessibility checks, layout audits, "does this look like a plot at all?" smoke tests.

---

## mos_visual_check — one-shot

```python
args:
  source: str
  format: "latex" | "html" | "md"
  question: str
returns: {
  image_path,
  description,
  issues: [...],
  verdict: "pass" | "warn" | "fail",
}
```

Equivalent to `_render` then `_inspect` in one call. Use this for CI-style "does my figure pass?" checks.

---

## Patterns

### Writer previewing a Section 4 figure

```python
mos_visual_check(
  source=open("paper/fig4.tex").read(),
  format="latex",
  question="Are the two regimes labeled distinctly? Is the colorbar readable?",
)
```

### Coder verifying a fresh experiment plot

```python
mos_visual_check(
  source=fig_html,
  format="html",
  question="Are val_acc=1.0 transitions visually obvious?",
)
```

---

## Pitfalls

- **Render cost is real** — 1-3 s per call. Don't render in a loop.
- **Vision-model inspection is opinionated.** Treat `verdict: warn` as "look again", not as a hard fail.
- **Don't render Noter's content.** Noter has no `branches/<role>/visual-reports/` and the tool will reject the call.
