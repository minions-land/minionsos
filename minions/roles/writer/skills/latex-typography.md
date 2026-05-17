---
slug: latex-typography
summary: LaTeX formatting conventions — model names via \newcommand macros, avoid itemize (except Introduction contributions), no \paragraph{} short heads, no gratuitous bold/italic, model names use \textsc.
layer: logical
tools:
version: 2
status: active
supersedes:
references: make-latex-model, paper-compile
provenance: R7-evolved
---

# Skill — LaTeX Typography

Typographic consistency signals professionalism. These conventions ensure the manuscript uses LaTeX's formatting capabilities deliberately rather than ad hoc, and avoids the structural anti-patterns that venue editors and reviewers associate with rushed submissions.

## When to invoke

- Polishing LaTeX formatting.
- Checking typographic convention compliance.

## Macro discipline

Define model/method names as macros at the preamble level:

```latex
\newcommand{\methodname}{\textsc{RetroDiff}\xspace}
```

This ensures renaming requires a single edit and font treatment remains consistent throughout. Use `\textsc{}` for model names; do not use `\texttt{}` (monospace is a code font, not a model-name font).

## Structural formatting

**No itemize outside Introduction contributions.** The only permitted `\begin{itemize}` in the paper is the contribution bullet list at the end of the Introduction. All other enumerations must be rewritten as prose.

**No `\paragraph{}` short heads.** Do not use `\paragraph{Step 1.}` style formatting. When subheadings are needed, use `\noindent\textbf{...}` or `\subsection{}`. A `\paragraph{}` followed by only one line of content indicates a structural problem that formatting cannot solve.

## Inline formatting

**Bold** is reserved for the first definition of a term. Do not scatter `\textbf{}` throughout the text for emphasis — sentence structure and position should carry emphasis, not formatting.

**Italic** is reserved for mathematical variables and foreign-language terms only.

## Pitfalls

- Model name appearing in inconsistent formats across the text (some bold, some monospace, some small-caps).
- `\paragraph{}` followed by only one line of content (indicates a structural problem).
- Excessive bold for emphasis (sentence structure and position should carry emphasis, not formatting).
