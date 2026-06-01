---
slug: writing-style
summary: Eliminate AI tone, translationese, redundancy, and code-level identifiers in body prose; use abstract scientific terminology and blacklist high-frequency AI words.
layer: logical
tools:
version: 3
status: active
supersedes:
references: cn-en-academic-polish
provenance: R7-evolved
---

# Skill — Writing Style

Academic prose should be invisible — the reader sees the argument, not the writing. AI-generated text and translationese both fail this test because they introduce recognizable patterns that distract from content. This skill operates at three levels: word choice, sentence structure, and paragraph rhythm.

## When to invoke

- Polishing prose style in any section.
- Checking for AI writing artifacts or literal-translation structures.

## Word choice

**Blacklisted AI markers.** Remove: delve, pivotal, landscape, tapestry, underscore, noteworthy, intriguingly, harness, leverage, utilize, multifaceted, paradigm shift, holistic. Replacements: delve → examine; pivotal → key; leverage → use; utilize → use.

**Translationese patterns.** These survive from Chinese-source drafts or AI generation:
- "With the rapid development of…" → start from the concrete problem
- "plays an important role" → "enables" / "is central to"
- "has attracted wide attention" → "is widely studied" or remove entirely

**Prefer verbs over nominalizations.** "perform an analysis" → "analyze"; "make a comparison" → "compare".

**Use specific nouns.** "this result" → "the 30× speedup" / "the convergence guarantee". Vague referents force the reader to backtrack.

**No code-level identifiers in body prose.** Code-level identifiers are forbidden in body sections: function names, file paths, folder names, version numbers, language/runtime requirements, package names, command names, and implementation labels. These belong in the Appendix or Methods-implementation supplement. Body text uses abstract scientific or engineering terminology only.

Replacement examples:
- `eacn3_create_subtask` → `the subtask-decomposition primitive`
- `mcp-servers/eacn3/` → `the coordination-bus implementation`
- `Python 3.11 package` → omit entirely, or write `the runtime` only if the runtime itself is scientifically relevant
- `five milestones: experiments_ready, writing_ready, ...` → `five milestones spanning the natural progression from experiment readiness to camera-ready submission`

## Sentence structure

**Keep subject and verb adjacent.** Do not insert long relative clauses between subject and verb.

**Given-before-new information order.** Each sentence: familiar context first → new information later. Place the most important new information at sentence end.

**Remove redundant openings.** Delete "It is worth noting that" / "Importantly," / "Notably," / "In this section, we…". These add no information.

## Paragraph rhythm

**Avoid consecutive This/We sentence openings.** Do not begin two consecutive sentences with "This" or "We".

**Avoid rule-of-three patterns.** Do not repeatedly use "X, Y, and Z" tricolon structures — this is a hallmark of AI-generated prose that reviewers recognize.

## Pitfalls

- Opening with "delve into" (the single most recognizable AI marker).
- Three consecutive sentences beginning with "We".
- Every paragraph containing an "X, Y, and Z" tricolon enumeration.
- "this approach" with unclear antecedent (forces the reader to backtrack).
- Code-level identifiers in body prose; replace implementation names with abstract terms and move substrate details to the Appendix.
