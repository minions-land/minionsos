# Skill — First-Principles Thinking

A reasoning discipline Expert should apply when forming hypotheses, evaluating proposals, or critiquing existing approaches.

## Core question

> What is actually true here, independent of what everyone already assumes?

Do not reason by analogy ("X worked for Y, so try it here"). Reason from the irreducible facts of the current problem: constraints, mechanisms, quantities, causal relationships. Analogy can suggest hypotheses; it cannot justify them.

## Procedure

1. **Strip assumptions.** List every premise the current proposal depends on. For each, ask: "Why do I believe this? Is the reason a first-principle fact, or convention / authority / aesthetic preference?" Mark the convention-based ones as load-bearing but unverified.
2. **Reduce to primitives.** Decompose the problem until you hit quantities or mechanisms you cannot further decompose within your domain (e.g. information-theoretic bounds, physical limits, provable guarantees, raw statistical properties of the data).
3. **Rebuild.** Re-assemble a solution starting only from the primitives. If the re-assembled solution matches the conventional one, the convention is justified. If it diverges, you have a candidate improvement — or you have missed a constraint.
4. **Name the divergence.** When your first-principle reconstruction disagrees with standard practice, articulate **exactly** which assumption the standard practice smuggled in that your reconstruction drops. This is the most valuable output.

## When to invoke

- When a proposal sounds reasonable but "because everyone does it that way" is the strongest argument for it.
- When the team is stuck inside a local optimum defined by the conventional framing.
- When evaluating a baseline, metric, or benchmark — is it measuring the thing we actually care about, or a proxy inherited from prior work?
- When asked to decompose a goal into subproblems: prefer decomposition along causal / mechanistic seams, not along the organizational / chapter structure of prior work.

## Pitfalls

- **Not every question benefits.** Engineering details (which library, which optimizer) rarely reward first-principles treatment; conventions are usually load-bearing for good reason. Reserve this skill for the 20% of questions where the framing itself is doing the damage.
- **Don't discard evidence.** First-principles ≠ ignoring empirical literature. It means re-deriving from primitives and *then* checking against what the literature has observed. Divergence from literature is a flag, not a license.
- **Avoid crank mode.** First-principles reasoning that rejects the entire field's accumulated evidence without new data is almost always wrong. Use this skill to refine, not to posture.

## Output habit

When you make a claim derived from this skill, mark it `[derived: first-principles from <primitive-list>]` in your EACN message, per root §9. This lets Ethics and the rest of the team see your reasoning chain, not just your conclusion.
