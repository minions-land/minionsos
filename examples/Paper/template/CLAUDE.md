# Template Directory Rules

- `template/` is a read-only reference directory.
- Do not directly edit files inside `template/`.
- Do not assume that this directory always contains a fixed entry filename, fixed style filename, or fixed compiled PDF filename.
- If paper writing needs to begin, inspect the files under `template/`, identify the relevant entry and support files, then copy the needed structure into `paper/` as the working copy.
- Preserve the overall template structure, style package usage, submission format, and venue constraints detected from the reference template.
- Do not modify `.sty` files just to accommodate content.
- If section content does not fit the template structure, adjust the organization of `paper/sections/*.tex` before considering any template source changes.
