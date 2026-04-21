---
name: "survey"
description: "Run a topic survey by orchestrating subagents for vertical literature review, horizontal recent-progress review, and reviewer scoring with sources."
paths:
  - "**/*"
---

# /survey

Use this skill when the user gives a research topic and wants a structured survey based on subagent orchestration rather than doing the research directly in the main thread.

## Purpose

Given a topic such as `machine learning`, produce a reliable survey by acting as the coordinator only:
- launch one subagent for a vertical literature review
- launch one subagent for a horizontal recent-progress review
- launch one reviewer subagent to assess relevance and reliability
- synthesize the approved findings into one final report

The main agent should not do broad literature searching itself unless needed to verify an obvious gap or resolve a contradiction. The main agent's job is orchestration, verification of outputs, and final synthesis.
This file is the canonical behavioral definition for the survey coordinator in this repository.

## Inputs

Expected user input:
- a topic or research question
- optional scope constraints
- optional language preference
- optional venue/domain hints

If the user provides no time range, interpret recent work as the last 2 to 3 years counted backward from today's system date.

## Required subagents

Always launch these subagents.

### 1) Vertical survey subagent

Use `Agent` with `subagent_type: "general-purpose"`.

Mission:
- identify the topic's core problem definitions, task settings, datasets, benchmarks, and representative methods
- cover work from the last 2 to 3 years relative to today's system date
- also include a short set of highly classic or foundational papers that are still essential for understanding the area
- collect source information for each item
- collect links for paper pages and open-source repositories when available

Required output structure:
- Topic framing
- Canonical problem settings
- Classic papers
- Recent 2 to 3 year timeline
- Key methods and trends
- Benchmarks/datasets
- Open problems
- Sources table with title, year, venue, paper link, code link, and why it matters

### 2) Horizontal survey subagent

Use `Agent` with `subagent_type: "general-purpose"`.

Mission:
- focus on what recent research is doing across the topic landscape
- summarize major directions, recurring techniques, evaluation patterns, and empirical progress
- answer explicitly: what are people trying now, what has improved, what still fails, what directions are emerging, and whether the core line of work is accelerating, slowing down, or fragmenting into sub-directions
- make the recent-work picture concrete rather than generic: identify whether the field still has a strong core track or has split into adjacent tracks
- collect source information for each claim
- collect links for paper pages and open-source repositories when available

Required output structure:
- What the field is doing now
- Whether the core research line is still active, slowing down, or fragmenting
- Recent directions
- Common technical patterns
- What progress has been achieved
- Limits and failure modes
- Emerging themes and branch directions
- Sources table with title, year, venue, paper link, code link, and supporting claim

### 3) Reviewer subagent

Use `Agent` with `subagent_type: "general-purpose"`.

Mission:
- review the outputs from the vertical and horizontal survey subagents
- check whether the findings are relevant to the exact topic
- check whether the sources look reliable and whether important claims are traceable to sources
- check whether the horizontal survey actually answers what the field is doing now rather than merely listing recent papers
- check whether the horizontal survey makes clear if the field's core line is still active, slowing down, or fragmenting into branch directions
- score each cited work or cluster of works from 0 to 10 on:
  - topic fit
  - source reliability
  - importance to the survey
- flag missing classics, irrelevant items, weak sources, outdated claims, over-generalizations, or a horizontal section that fails to explain the recent research landscape clearly

Required scoring rubric:
- 0 to 2: irrelevant, unreliable, or unsupported
- 3 to 4: weak fit or weak evidence
- 5 to 6: acceptable but not central
- 7 to 8: strong, relevant, and useful
- 9 to 10: highly relevant, reliable, and near-essential

Reviewer output must include:
- accepted items
- questionable items
- rejected items
- missing but should-have-been-included items
- a concise justification for each low score
- an overall confidence score from 0 to 10 for the final survey package

## Execution rules

- Launch the vertical and horizontal subagents in parallel.
- After both return, launch the reviewer subagent with both outputs as input.
- Trust but verify: do not present a subagent finding as final unless it survived reviewer scrutiny or was explicitly caveated.
- Prefer papers from strong venues, arXiv papers with clear impact, or widely used benchmark/code releases.
- For code links, prefer official repositories. If unofficial, label them clearly.
- For paper links, prefer the paper landing page, arXiv page, or official venue page. Do not invent URLs.
- Every major claim in the final report must be backed by at least one source.
- If the topic is ambiguous, narrow it before searching. Example: ask whether `视觉长尾` means long-tailed recognition, detection, segmentation, or general long-tailed visual learning.

## Recommended agent prompts

### Prompt template for the vertical survey subagent

"Conduct a vertical literature survey on the topic: <TOPIC>. Cover recent work from the last 2 to 3 years relative to today's system date, plus a concise set of classic/foundational papers that are still essential. Focus on problem definition, major method families, datasets/benchmarks, and open problems. For every important item, provide source information, a paper link, and an open-source code link when available. Report in structured sections and include a compact sources table."

### Prompt template for the horizontal survey subagent

"Conduct a horizontal survey on the topic: <TOPIC>. Focus on what recent research is doing now: major directions, technical patterns, progress achieved, limits, and emerging themes, mainly from the last 2 to 3 years relative to today's system date. Make explicit whether the field still has a strong core line of work or whether recent research has fragmented into adjacent branch directions, and identify what researchers are actually trying now rather than only listing papers. Every major claim must have source information. Include paper links and open-source code links when available. Report in structured sections and include a compact sources table."

### Prompt template for the reviewer subagent

"Review two survey drafts on the topic: <TOPIC>. Evaluate whether the included works are relevant, reliable, and well-supported. Score each cited work or cluster from 0 to 10 on topic fit, source reliability, and importance. Identify accepted, questionable, rejected, and missing items. Give brief reasons for low scores and an overall confidence score from 0 to 10 for the survey package."

## Final response format

Return a concise but information-dense report with these sections:

1. Topic
2. Scope used
3. Vertical survey summary
4. Horizontal survey summary
5. Reviewer assessment
6. Recommended reading list
7. Source appendix

### Reviewer assessment section format

Include:
- Overall confidence: X/10
- Strongly recommended papers/items
- Questionable or weakly supported items
- Missing classics or recent works to add

### Source appendix requirements

For each source, list:
- title
- year
- venue
- paper link
- code link
- which section or claim it supports
- reviewer score: 0 to 10

## Quality bar

A good result should:
- clearly separate classic work from recent work
- clearly separate vertical and horizontal perspectives
- include concrete sources instead of vague summaries
- include code and paper links whenever available
- expose uncertainty instead of hiding it
- let the user quickly see which items are most trustworthy through the reviewer scores
