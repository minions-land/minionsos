---
slug: methodology-discipline
summary: Method section defines contribution-level mechanisms while separating body science from Appendix implementation substrate; no code-level identifiers in body sections.
layer: logical
tools:
version: 3
status: active
supersedes:
references: end-to-end-paper-workflow
provenance: R7-evolved
---

# Skill — Methodology Discipline

The Method section is the technical core of the paper. It must be self-contained at the scientific and engineering-contribution level: a reader with the right background should understand the mechanism, abstractions, and evidence-bearing design choices without reading repository plumbing. The structure flows from notation setup through modular description to algorithmic specification, with every design choice traceable to an experimental verification.

## When to invoke

- Drafting or polishing the Method / Approach section.

## Setup

Define notation at the beginning, referencing `math_commands.tex`. The reader should not encounter undefined symbols when reading equations. This front-loads the cognitive cost so the technical exposition flows without interruption.

## Body vs Appendix

The body contains only scientific and engineering contributions: the abstraction, mechanism, coordination protocol, formalization, algorithmic structure, and why those choices matter. The Appendix contains implementation substrate: repository layout, package structure, configuration, language/runtime versions, command-line invocations, file paths, function names, folder names, and other engineering plumbing.

Code-level identifiers are forbidden in body sections. Function names, file paths, folder names, version numbers, language/runtime requirements, package names, command names, and milestone identifiers live in the Appendix only. Body text uses abstract terminology.

Replacement examples:
- `eacn3_create_subtask` → `the subtask-decomposition primitive`
- `mcp-servers/eacn3/` → `the coordination-bus implementation`
- `Python 3.11 package` → omit entirely, or write `the runtime` only if scientifically relevant
- `five milestones: experiments_ready, writing_ready, ...` → `five milestones spanning the natural progression from experiment readiness to camera-ready submission`

## Module structure

Organize the method into one subsection per module. Each subsection contains four elements: input, output, core formula, and design motivation. This modular structure allows the reader to understand each component independently before seeing how they compose.

For multi-step processes, provide an `algorithm2e` or `algorithmic` environment that specifies the complete procedure. Prose retains only the high-level description and intuition; the pseudocode carries the precise specification.

## Cross-references

Every design choice in the Method must have a corresponding verification in the Experiments section. If a choice cannot be verified experimentally, it should be justified theoretically or acknowledged as a heuristic.

The Method section does not restate motivation from the Introduction. When context is needed, reference the Introduction in a single sentence and move on.

## Pitfalls

- All equations packed into a single large paragraph without modular separation.
- No algorithm pseudocode, making the method non-reproducible for the reader.
- Rewriting a motivation paragraph that wastes page budget and duplicates the Introduction.
- Body sections filled with implementation substrate such as repository layout, runtime versions, package structure, file paths, or command-line invocations.
- Code-level identifiers in body text; replace them with contribution-level terminology and move exact implementation details to the Appendix.
