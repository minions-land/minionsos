---
name: "multidisciplinary-debate"
description: "Coordinate long-running evidence-first debate among expert subagents for research, experiment design, and writing, with the main agent acting only as orchestrator and judge."
paths:
  - "**/*"
---

# /multidisciplinary-debate

Use this skill when the user wants a long-running, evidence-first workflow driven by multiple expert subagents rather than direct analysis in the main thread.

## Purpose

Given a research question, experiment goal, or writing objective, produce a defensible output by acting as the coordinator only:
- select the minimum necessary experts from the provided agent cards
- launch subagents with explicit domain identities and scope limits
- require each expert to gather evidence before debating
- run structured multi-round debate with targeted rebuttals
- judge claims by evidence strength, methodological quality, and rebuttal survival
- synthesize the final conclusion without adding new domain claims in the main agent

The main agent must not perform substantive domain reasoning of its own. Its job is orchestration, admissibility control, evidence tracking, and final adjudication.
This file is the canonical behavioral definition for multidisciplinary expert debate in this repository.

## Inputs

Expected user input:
- task_type: `research` | `experiment` | `writing`
- objective: the concrete problem to solve
- deliverable: expected output format
- agent_cards: available expert identities and domains
- optional constraints: time budget, round limit, citation style, source scope, language, MCP tools allowed
- optional evaluation priorities: novelty, rigor, feasibility, clarity, publication readiness, experimental risk

If the user does not give a round count, default to 3 debate rounds for normal tasks and 5 rounds for high-stakes or highly disputed tasks.

## Required role policy

### Main agent

The main agent is the orchestrator and judge only.

Must do:
- read the task and identify which expert domains are required
- pick only the minimum useful expert set from the provided agent cards
- define the debate question, output target, and evaluation rubric
- launch and coordinate subagents
- keep a claim ledger across rounds
- decide which claims are admissible, accepted, rejected, or unresolved
- produce the final report strictly from surviving evidence-backed claims

Must not do:
- introduce its own domain claims
- fill evidence gaps with intuition
- resolve disputes by style, confidence, or verbosity
- silently merge contradictory claims without marking the conflict

### Expert subagents

Each subagent must:
- stay within its assigned agent card domain
- state assumptions explicitly
- separate facts, interpretations, and recommendations
- support every substantial claim with evidence
- attack specific prior claims during rebuttal rather than vaguely disagreeing
- revise or withdraw claims when rebuttals succeed

## Evidence admissibility rules

Every substantial claim must include:
- claim text
- evidence source
- why the source supports the claim
- confidence score from 0 to 1
- limitation or caveat

A claim is inadmissible if it:
- has no evidence
- cites a source that does not actually support it
- goes beyond the expert's assigned domain without explicit justification
- relies only on assertion, rhetoric, or vague common knowledge

For disputed high-impact claims, require verification through allowed tools such as MCP literature lookup.
Prefer strong surveys, seminal papers, strong empirical studies, benchmarks, and recent high-quality work over weak or derivative sources.

## Required subagent workflow

Always run these stages.

### 1) Expert selection stage

Mission for the main agent:
- inspect the objective and deliverable
- choose the minimum useful set of domain experts from the provided agent cards
- avoid redundant experts unless the user explicitly wants overlap
- define each expert's role in one sentence

Required output for this stage:
- selected experts
- excluded experts and why
- role assignment table
- evaluation rubric for the debate

### 2) Independent evidence brief stage

Use `Agent` for each selected expert.

Mission for each expert:
- independently analyze the task within domain scope
- gather evidence before reading opponents' arguments when possible
- produce an initial brief grounded in sources

Required output structure for each expert:
- domain perspective
- top claims
- supporting evidence for each claim
- assumptions
- known weaknesses or boundary conditions
- confidence scores
- open questions that need cross-domain challenge

### 3) Structured debate stage

Use `Agent` for each selected expert.

Mission:
- debate across multiple rounds
- target specific prior claims from other experts
- expose methodological flaws, scope mismatch, unsupported extrapolation, confounders, alternative explanations, or writing weaknesses
- defend, revise, or withdraw earlier claims based on criticism

Required rules per debate turn:
- every rebuttal must reference a concrete prior claim
- every rebuttal must explain why the target claim is weak, incomplete, or incorrect
- every defense must answer the strongest attack directly
- experts must update confidence when challenged
- unsupported rebuttals are inadmissible just like unsupported claims

Track each debated item in this structure:
- claim_id
- originating expert
- claim
- evidence
- attacks received
- defense or revision
- current status: `active` | `weakened` | `revised` | `withdrawn`

### 4) Evidence cross-check stage

Use `Agent` or allowed MCP tools for verification when needed.

Mission:
- cross-check disputed high-impact claims
- verify whether cited papers or sources actually support the stated conclusion
- identify when experts are talking past each other because of different assumptions or task definitions

Required output structure:
- verified claims
- unsupported or overstated claims
- claims that depend on hidden assumptions
- claims that are actually compatible after scope clarification

### 5) Adjudication stage

The main agent judges only.

Judge scoring rubric for each surviving claim:
- evidence quality
- methodological soundness
- cross-domain consistency
- rebuttal survival
- actionability for the user's deliverable

Score each dimension from 0 to 10 and explain any score below 6.

Required adjudication buckets:
- accepted claims
- rejected claims
- unresolved claims
- claims needing further evidence

### 6) Final output stage

The final output must be derived only from accepted claims plus explicitly marked unresolved points.

## Task-specific output templates

### For `research`

Return:
- research question
- scope used
- expert lineup
- accepted findings
- strongest counterarguments
- unresolved disagreements
- evidence matrix
- literature gaps
- recommended next reading or validation steps
- bibliography

### For `experiment`

Return:
- objective and hypothesis
- expert lineup
- accepted assumptions
- debated risks and confounders
- final experimental design
- variables and controls
- metrics and success criteria
- failure interpretation plan
- unresolved uncertainties
- evidence appendix

### For `writing`

Return:
- writing objective
- target audience and stance
- expert lineup
- accepted thesis points
- strongest objections and responses
- recommended structure or outline
- evidence-backed section plan
- claims to avoid or soften
- unresolved issues needing more support
- bibliography or source appendix

## Execution rules

- The main agent should launch expert evidence-brief subagents in parallel when independent.
- Debate rounds may run in parallel by collecting all rebuttals to the current claim set, then consolidating before the next round.
- The main agent should intervene only to enforce structure, admissibility, and scoring.
- Do not let any expert dominate due to verbosity; score by evidence quality.
- Prefer direct citations and concrete findings over broad summaries.
- When experts disagree because they use different definitions, force definition alignment before another round.
- When a claim remains high-impact and unresolved after the planned rounds, mark it unresolved rather than forcing consensus.
- Long-running tasks may include additional retrieval rounds through MCP literature tools before final adjudication.

## Recommended agent prompts

### Prompt template for expert evidence brief

"You are the selected expert for domain: <DOMAIN>. Your role is: <ROLE>. Stay strictly within this domain unless you explicitly mark a cross-domain inference. Analyze the task: <OBJECTIVE>. Produce an evidence-first brief with top claims, supporting evidence, assumptions, weaknesses, confidence scores, and open questions for other experts to challenge. Every substantial claim must include a source, why it supports the claim, a confidence score, and a limitation. Unsupported claims are inadmissible."

### Prompt template for debate round

"You are participating in a structured expert debate for the task: <OBJECTIVE>. Review the current claim ledger and target only specific claims made by other experts. For each rebuttal, name the target claim, explain the flaw or limitation, provide evidence if available, and state whether the claim should be weakened, revised, or rejected. If defending your own earlier claim, answer the strongest attack directly and revise your confidence if needed. Unsupported rebuttals are inadmissible."

### Prompt template for evidence cross-check

"Verify the disputed high-impact claims in this expert debate for the task: <OBJECTIVE>. Check whether the cited sources actually support each claim, whether key assumptions were left implicit, and whether apparent conflicts are real or just definition mismatches. Return verified claims, unsupported or overstated claims, hidden assumptions, and claims that become compatible after scope clarification."

### Prompt template for judge synthesis

"Act only as the judge and orchestrator for the task: <OBJECTIVE>. Do not add new domain claims. Using the claim ledger, evidence briefs, rebuttals, and verification notes, score each surviving claim on evidence quality, methodological soundness, cross-domain consistency, rebuttal survival, and actionability. Produce accepted claims, rejected claims, unresolved claims, and a final deliverable that uses only accepted claims plus explicitly marked uncertainties."

## Final response format

Return a concise but high-density report with these sections:

1. Task type
2. Objective
3. Expert lineup and roles
4. Evaluation rubric used
5. Accepted claims
6. Strongest rejected or weakened claims
7. Unresolved disagreements
8. Final deliverable
9. Evidence appendix

### Evidence appendix requirements

For each major accepted or unresolved claim, list:
- claim_id
- originating expert
- claim text
- evidence source
- why the evidence supports or fails to support the claim
- confidence
- judge scores
- final status

## Quality bar

A good result should:
- keep the main agent out of substantive domain reasoning
- make every important claim traceable to evidence
- make rebuttals specific rather than rhetorical
- show clearly why one claim survived over another
- preserve unresolved uncertainty instead of pretending consensus
- produce a deliverable that is usable for research, experiment planning, or writing
