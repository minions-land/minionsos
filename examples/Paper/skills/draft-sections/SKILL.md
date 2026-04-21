---
name: draft-sections
description: "Draft or revise manuscript sections in LaTeX while preserving scientific correctness"
---

# /draft-sections — Draft or Revise Sections

Draft or revise manuscript sections in LaTeX.

## Goal

Produce polished section text while keeping the underlying science intact.

## Typical sections

- abstract
- introduction
- methods framing
- results presentation
- discussion
- limitations
- appendix-facing material if needed

## Do

- improve clarity and readability
- improve structure and transitions
- adapt wording to the paper's current evidence state
- directly update the paper directory when appropriate

## Do not do

- do not invent results
- do not add unsupported scientific claims
- do not silently change the meaning of core findings

## Output

Return either:
- revised section text
- a LaTeX-ready patch plan
- a list of section-level issues that block writing