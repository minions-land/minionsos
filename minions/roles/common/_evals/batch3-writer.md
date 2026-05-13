# Batch: writer

## Per-skill grades

| slug | summary | trigger | procedure | pitfalls | structure | mean | verdict |
|---|---|---|---|---|---|---|---|
| abstract-writing | 5 | 4 | 5 | 4 | 5 | 4.6 | KEEP |
| academic-plotting | 5 | 5 | 5 | 4 | 5 | 4.8 | KEEP |
| citation-audit | 5 | 5 | 5 | 5 | 5 | 5.0 | KEEP |
| end-to-end-paper-workflow | 5 | 4 | 4 | 4 | 4 | 4.2 | KEEP |
| figure-spec | 5 | 5 | 5 | 4 | 5 | 4.8 | KEEP |
| imported-paper-skill-catalog | 3 | 2 | 3 | 3 | 3 | 2.8 | TUNE |
| interactive-figure-prototype | 4 | 3 | 4 | 4 | 5 | 4.0 | TUNE |
| make-latex-model | 5 | 4 | 5 | 4 | 5 | 4.6 | KEEP |
| package-submission | 5 | 4 | 5 | 5 | 5 | 4.8 | KEEP |
| paper-compile | 5 | 4 | 5 | 4 | 5 | 4.6 | KEEP |
| paper-search-tools | 5 | 4 | 5 | 4 | 5 | 4.6 | KEEP |
| paper-work-boundaries | 4 | 2 | 4 | 3 | 3 | 3.2 | TUNE |
| prepare-rebuttal | 5 | 4 | 5 | 5 | 5 | 4.8 | KEEP |

## Per-skill notes

### abstract-writing
- **Verdict:** KEEP
- **Strengths:** Six-rung ladder with strict word budgets is immediately executable; evidence-tagging convention is explicit.
- **Issues:** Trigger "Preparing a general-audience abstract for a broad scientific venue" is vague — it overlaps with the first two triggers and adds no new decision boundary.
- **Recommended action:** Collapse the third trigger into the second or sharpen it to a concrete scenario (e.g. "venue requires a separate lay summary").

### academic-plotting
- **Verdict:** KEEP
- **Strengths:** Tool-choice table, chart-type-from-data-shape table, exact Okabe-Ito hex codes, and the three-file output contract are all immediately actionable.
- **Issues:** "Over-decorating: gradients, 3D bars, drop shadows" is the weakest pitfall — it names symptoms but not the failure mode (reviewer distrust, journal rejection for non-reproducible raster).
- **Recommended action:** Minor — expand that pitfall line to name the consequence, not just the symptom.

### citation-audit
- **Verdict:** KEEP
- **Strengths:** Three-layer check (existence / metadata / context) is a concrete, non-obvious framework; `WRONG_CONTEXT` as the most dangerous class is a genuine insight; dual output format (`.md` + `.json`) is precise.
- **Issues:** No issues worth flagging. The timing gate ("after draft stable, before final compile") is one of the clearest trigger constraints in the batch.
- **Recommended action:** None.

### end-to-end-paper-workflow
- **Verdict:** KEEP
- **Strengths:** Seven-phase pipeline with explicit blockers list prevents premature "done" declarations; EACN escalation path for missing evidence is named.
- **Issues:** Step 2 delegates to `paper-evidence-analyst` and step 3 to `paper-literature-citation-builder` — these subagent names are defined in `paper-work-boundaries`, but a fresh agent reading only this file does not know that. The phrase "delegate by boundary" in step 4 is opaque without the cross-reference. The `layer: composite` metadata is correct but the skill does not explain what composite means for invocation order.
- **Recommended action:** Add a one-sentence inline note at step 4 pointing to `paper-work-boundaries` for the boundary map, so the skill is self-contained enough to act on without opening a second file.

### figure-spec
- **Verdict:** KEEP
- **Strengths:** Four-block JSON schema with exact canvas dimensions, edge style semantics, and the provenance-comment requirement are all concrete and copy-pasteable.
- **Issues:** "Letting a diagram tool auto-layout" pitfall is good but does not name which tools are the common offenders (Mermaid, draw.io auto-arrange, Graphviz dot). A fresh agent might not recognize the risk.
- **Recommended action:** Minor — name one or two common auto-layout tools in the pitfall line.

### imported-paper-skill-catalog
- **Verdict:** TUNE
- **Strengths:** Prevents a real failure mode (assuming external `.codex/skills` files exist); the grouped synonym list is useful reference.
- **Issues:** Trigger "When a user explicitly names one of the imported skill names listed below" is the weakest trigger in the batch — it requires the agent to already be reading this file to know when to open it. The summary "Map imported claude_write paper-writing skill names onto Writer's local workflow" describes a historical migration artifact, not an ongoing operational need. The `layer: scheduling` classification is questionable — this is closer to a reference/glossary than a scheduling discipline. The procedure (3 steps) is thin: step 2 says "treat the name as a task category" without specifying how to communicate that to the user or EACN.
- **Recommended action:** Reframe as a reference appendix rather than an active skill, or merge the synonym table into `end-to-end-paper-workflow` as a "known aliases" section and drop this file.

### interactive-figure-prototype
- **Verdict:** TUNE
- **Strengths:** Prototype path convention, the "name the figure decision" first step, and the static-extraction handoff are all concrete.
- **Issues:** Trigger "A figure is important but the best static presentation is unclear" is subjective — "important" and "unclear" give no decision threshold. A fresh agent cannot tell when this skill applies vs. just drafting a figure directly. The pitfall "Spending prototype time on routine plots that already have a clear spec" acknowledges the ambiguity but does not resolve it. The skill also does not specify what technology to use for the HTML prototype (vanilla JS, Plotly, Vega-Lite) — "local interactive HTML explorer" is underspecified for execution.
- **Recommended action:** Add a concrete decision rule to the trigger (e.g. "figure has ≥ 3 independent visual choices: grouping, metric, ordering, annotation") and name at least one recommended JS library.

### make-latex-model
- **Verdict:** KEEP
- **Strengths:** Directory layout, two-digit section prefix convention, citation-command-by-venue table, and the `% [VERIFY]` marker pattern are all immediately actionable.
- **Issues:** "When switching venue — re-scaffold, do not patch the old one" is a good trigger but the procedure does not explain what to do with the existing `branches/writer/paper/` content (archive it? rename it?). Step 1 says "fetch the official style file from the venue page" but does not name where to find venue pages for the listed venues (ICLR/NeurIPS/ICML etc.) — a fresh agent might search incorrectly.
- **Recommended action:** Add one sentence to step 1 naming the canonical style-file sources (e.g. openreview.net for ICLR, neurips.cc for NeurIPS) and one sentence to the venue-switch trigger about archiving the old scaffold.

### package-submission
- **Verdict:** KEEP
- **Strengths:** `tex.zip` exclusion list, standalone-compile verification step, `pdffonts` command, and the reproducibility-claim tagging convention are all precise and executable.
- **Issues:** "Code snapshot that reproduces 'something close' rather than the claimed numbers" is the best pitfall in the batch — concrete and non-obvious. The file-size guidance ("typically < 50 MB; prefer < 10 MB") is a reasonable heuristic but not sourced; a fresh agent might apply it to a venue with a different limit.
- **Recommended action:** Minor — note that file-size limits should be verified against the current venue CFP, not assumed from the heuristic.

### paper-compile
- **Verdict:** KEEP
- **Strengths:** Exact shell commands (`latexmk -C`, `grep "Overfull \\hbox"`, `pdffonts main.pdf | grep -v yes`), the 3-attempt cap with the "must change at least one concrete source line" rule, and the stale-section detection step are all immediately executable.
- **Issues:** "Auto-deleting `\usepackage` lines to clear errors — often removes load-bearing macros" is a good pitfall but does not name the specific packages most commonly deleted incorrectly (e.g. `hyperref`, `cleveref`). The trigger "Whenever `[VERIFY]` markers, `?` refs, or overfull warnings are suspected" is slightly weak — "suspected" is not a concrete condition.
- **Recommended action:** Minor — replace "suspected" with "present in the source or last compile.log".

### paper-search-tools
- **Verdict:** KEEP
- **Strengths:** Tool names are listed in frontmatter `tools:` field (machine-readable), fallback path is explicit, and "never fabricate BibTeX" is a concrete prohibition with a concrete alternative (mark a citation gap).
- **Issues:** "Verify before citing. Do not trust a search result title alone" is good advice but the procedure does not specify what "verify" means — read the abstract? read the full paper? The threshold is left to judgment.
- **Recommended action:** Minor — add a one-line rule: "For claims about methods or results, read at minimum the abstract and conclusion; for existence-only citations, abstract is sufficient."

### paper-work-boundaries
- **Verdict:** TUNE
- **Strengths:** The ten-subagent boundary table is the most useful reference in the batch for delegation decisions; required final report sections are explicit.
- **Issues:** Trigger "Every time Writer spawns a paper-* subagent" is a usage instruction, not a decision trigger — it tells the agent when to use the skill but not how to recognize that it is about to spawn a subagent. The `layer: scheduling` classification is correct but the skill reads more like a reference card than a procedure. The procedure section is a single sentence ("pick the one that matches") — there is no guidance on what to do when the work spans multiple subagent slots (e.g. a figure that requires both `paper-figure-python` and `paper-results-writer` context). The pitfall "Letting a subagent write outside its slot" is real but gives no detection mechanism.
- **Recommended action:** Add a short decision rule for cross-slot work (e.g. "pass read-only context from one subagent's output to the next; never give two subagents write access to the same file") and add a detection hint to the slot-violation pitfall (e.g. "check `Files Changed` in the subagent report against the slot's allowed paths").

### prepare-rebuttal
- **Verdict:** KEEP
- **Strengths:** Response-type classification table, the "do not work from individual reviews alone" rule, the honesty audit step, and the "reviewers skim — keep blocks short" constraint are all concrete and non-obvious.
- **Issues:** "Responding issue-by-issue in review order instead of grouping" is the best pitfall in the batch. The only weak spot: step 4 says "do not wait on speculative experiments outside the rebuttal window" but does not define what makes an experiment speculative vs. feasible within the window — a fresh agent might still over-promise.
- **Recommended action:** Minor — add a one-line heuristic for feasibility (e.g. "an experiment is feasible within the rebuttal window only if Experimenter confirms it can complete in < 48 h with existing infrastructure").

## Batch-level observations

- **Overall quality is high.** Ten of thirteen skills score ≥ 4.0 mean. The batch is the strongest reviewed so far — concrete commands, exact file paths, and non-obvious pitfalls are the norm rather than the exception.
- **Two structural outliers.** `imported-paper-skill-catalog` and `paper-work-boundaries` are reference cards masquerading as procedural skills. Both have weak triggers and thin procedures. Consider whether they belong as skills at all or as appendices to `end-to-end-paper-workflow`.
- **Trigger weakness is the most common deficiency.** Seven skills have trigger language that includes at least one vague condition ("important", "unclear", "relevant", "suspected"). The best triggers in the batch (`citation-audit`, `academic-plotting`) name a concrete event or artifact state.
- **Cross-reference dependency.** `end-to-end-paper-workflow` → `paper-work-boundaries` → subagent names is a three-hop chain a fresh agent must traverse. The composite skill should inline enough of the boundary map to be actionable without opening a second file.
- **No redundancy detected.** `academic-plotting` and `figure-spec` are correctly scoped (numerical vs. structural); `interactive-figure-prototype` is correctly scoped as a pre-commit exploration tool. No merges recommended beyond the possible `imported-paper-skill-catalog` consolidation.
- **Gap: revision workflow.** There is no skill covering the camera-ready revision cycle (incorporating reviewer-requested changes into the manuscript after rebuttal acceptance). `prepare-rebuttal` covers the response; `package-submission` covers the final bundle; the middle step (revise manuscript per accepted changes, update figures/tables, re-run QA) is undocumented.
