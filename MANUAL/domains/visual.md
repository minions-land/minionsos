---
id: domain-visual
kind: domain
domain: visual
auth: [coder, writer, ethics, expert, gru]
source: minions/tools/mcp/visual_tools.py:122
since: stable
keywords: [visual, render, latex, html, inspect, image, figure]
related: [mos_visual_render, mos_visual_inspect, mos_visual_check]
status: stable
---

# Domain: Visual render

Render LaTeX / HTML / Markdown → image, then optionally inspect with a vision
model. Available to every EACN role except Noter.

## Top tools

```bash
lookup.py --id mos_visual_render    # source → image
lookup.py --id mos_visual_inspect   # image → vision-model report
lookup.py --id mos_visual_check     # render + inspect + verdict in one call
```

## Rules

- LaTeX `\input{}` does not resolve external files unless they're in the
  role's branch. Pass self-contained source.
- For long CJK / multi-section LaTeX (Tier-0 trigger from `CLAUDE.md`),
  seed a `.tex` file via `reliable-file-io` first, then render via path.
  Never pass the whole source as one tool input.
- Render cost ≈ 1-3 s per call. Don't render in a loop.
- Output persists under `branches/<role>/visual-reports/`.
