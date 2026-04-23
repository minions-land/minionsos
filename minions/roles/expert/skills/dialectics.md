# Skill — Dialectical Reasoning

A reasoning discipline Expert should apply when a proposal, hypothesis, or result feels "obviously right" — or when two Expert voices disagree.

## Core move

> Thesis → Antithesis → Synthesis.

Every strong position contains its own limitation. Surfacing the limitation before you commit to the position is how you avoid overfitting to a single frame.

## Procedure

1. **Thesis.** State the proposal as strongly as possible. Steelman it — make the best version of the argument, not a convenient caricature.
2. **Antithesis.** Construct the most plausible opposing position. This is not "random doubt"; it is a specific claim that, if true, would invalidate or substantially weaken the thesis. Where would the thesis break? What regime / dataset / assumption would reverse its conclusion?
3. **Contradiction inventory.** List the concrete points where thesis and antithesis conflict. Each conflict is either a testable claim (→ experiment) or a conditional assumption (→ scope statement). Do not paper over conflicts with "it depends."
4. **Synthesis.** Integrate by finding the higher-level statement that accounts for both. Often this is a conditional: "Thesis holds when <condition>; antithesis holds when <¬condition>." Sometimes it is a reframing that dissolves the apparent conflict by revealing the two positions were answering different questions.
5. **Verify.** A genuine synthesis makes new predictions that neither the thesis nor the antithesis alone made. If your synthesis predicts nothing new, it is probably a compromise, not a synthesis.

## When to invoke

- When you are about to publish a confident claim.
- When two Experts (or Expert and Reviewer) disagree and both have evidence.
- When evaluating an experimental result that "just works" on your data — what regime would break it?
- When interpreting a surprising outcome: one frame will overfit to the finding; the opposing frame guards against that.
- When shaping paper claims: a dialectically tested claim survives review better than a monolithic one.

## Specific patterns to watch for

- **Scale-dependence dialectic.** Thesis holds at small scale; antithesis appears at large scale (or vice versa). Always ask: does this claim survive a 10× change in data / model / compute?
- **Distribution-dependence dialectic.** Thesis holds in-distribution; antithesis appears OOD. Always ask: what distribution shift would flip this?
- **Metric dialectic.** Thesis wins on metric A; antithesis wins on metric B. Always ask: what does the user actually care about, and is there a metric that captures it?
- **Short-term / long-term dialectic.** Thesis optimizes near-term; antithesis optimizes long-term. Common trap in training-dynamics and RL.

## Pitfalls

- **False-balance trap.** Some theses are simply correct and have no meaningful antithesis. Manufacturing one to look rigorous is worse than stating the thesis directly. Use this skill when you actually suspect a limitation, not ritually.
- **Relativism trap.** "Both sides have a point" is not a synthesis; it is giving up. A synthesis must be a concrete statement that predicts new things.
- **Infinite regress.** Every synthesis becomes a new thesis with a new antithesis. Do not recurse forever; stop when further decomposition stops changing your recommended action.

## Output habit

When you present a position refined through this skill, state the antithesis you considered and why the synthesis survives it. Mark the claim `[derived: dialectical synthesis of <thesis> vs <antithesis>]` per root §9. A single-frame claim without a considered antithesis invites an Ethics flag for unmarked speculation.
