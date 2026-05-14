# Stage B Coherence — writer cluster (14 skills)

Audit date: 2026-05-14. Read-only review of every skill body in `minions/roles/writer/skills/`. Cross-checked against `minions/roles/ethics/skills/citation-authenticity-audit.md` for lane overlap.

## Bucket summary

| Skill | Bucket | Confidence |
|---|---|---|
| abstract-writing | COHERENT | high |
| academic-plotting | COHERENT | high |
| apply-revisions | COHERENT | high |
| citation-audit | COHERENT | medium (lane vs ethics is implicit) |
| end-to-end-paper-workflow | COHERENT | high (clean orchestrator) |
| figure-spec | COHERENT | high |
| imported-paper-skill-catalog | COHERENT | medium (slim, but on-purpose) |
| interactive-figure-prototype | COHERENT | high |
| make-latex-model | COHERENT | high |
| package-submission | COHERENT | high |
| paper-compile | COHERENT | high |
| paper-search-tools | NEEDS POLISH | medium (mixes tool reference + how-to-search advice) |
| paper-work-boundaries | COHERENT | high (declarative, with thin verification procedure) |
| prepare-rebuttal | COHERENT | high |

Counts: COHERENT 13, NEEDS POLISH 1, NEEDS REWRITE 0, STITCHED-TOGETHER 0.

No 缝合怪 in the cluster. Cross-skill seams are intentional and lanes mostly hold up.

## Per-skill verdicts

### writer/abstract-writing — COHERENT
Single load-bearing trigger ("Drafting or rewriting the paper abstract"), single core move (six-rung ladder). Structure / Procedure / Pitfalls all tell the same story.
Evidence: summary "Layered scientific abstract from broad context to result, knowledge delta, and significance" matches the body's six numbered rungs. Pitfalls re-attack the same six rungs ("Starting with method mechanics instead of field-level motivation").
No recommendation.

### writer/academic-plotting — COHERENT
Tool guide for matplotlib data plots. The "Tool choice by figure shape" table draws a clear lane border to `figure-spec` for boxes-and-arrows; the rest of the body stays on numerical-axes plots.
Evidence: "Numbers → matplotlib; structure → diagram. Then style to venue, highlight 'our method' deliberately". Body follows that formula. No drift into spec format or interactive prototyping.
No recommendation.

### writer/apply-revisions — COHERENT
Single trigger (Reviewer publishes Weak Accept / Borderline OR rebuttal accepted) and single artifact (`revisions/round-<n>.md` checklist). Procedure threads cleanly into `citation-audit` re-run and `paper-compile`, then hands off to `package-submission`.
Evidence: "Bridge between `prepare-rebuttal` (which produces the response packet) and `package-submission` (which builds the final bundle)". Body stays inside that bridge.
No recommendation.

### writer/citation-audit — COHERENT (medium confidence)
Three-layer per-entry verdict, single output pair (`CITATION_AUDIT.md` + `.json`). Tightly scoped.
Evidence: "Every bib entry checked at three layers: the work exists, the metadata matches canonical sources, the context in our sentence is something the cited paper actually establishes".
Concern: scope split vs `ethics/citation-authenticity-audit` is not stated in either file. Both audit existence + metadata + context, both classify into roughly OK/DRIFT/WRONG_CONTEXT/MISSING-or-FABRICATED. The de-facto lanes (writer = full sweep before submission; ethics = sampled watchdog covering both Writer's `.bib` and Reviewer-cited prior work) work, but a one-line "this skill is the writer-side full sweep; Ethics owns sampled oversight via citation-authenticity-audit" would prevent future drift. See cross-skill section.
Recommendation: small polish — add one sentence delineating writer-side vs Ethics-side scope.

### writer/end-to-end-paper-workflow — COHERENT (clean orchestrator)
This is the file most at risk of becoming a 缝合怪 and it does not. The seven-phase procedure delegates by subagent slot (`paper-evidence-analyst`, `paper-literature-citation-builder`, `paper-qa-auditor`, etc.) and points to `paper-work-boundaries` for the boundary map; it does not re-implement abstract-writing, citation-audit, paper-compile, or package-submission.
Evidence: "Delegate by boundary per `paper-work-boundaries`: frontmatter, method, results, closing, figures, tables, template integration, QA". And: "If evidence is missing, stop and ask Expert / Experimenter / Coder / Gru / user through EACN — do not invent or rerun results inside Writer." Voice is orchestrator throughout.
Minor note: frontmatter `references` lists `citation-audit / paper-compile / package-submission / apply-revisions / prepare-rebuttal` but the procedure invokes them only via subagent slots and downstream skills. That is fine for a composite skill, just worth knowing.
No recommendation.

### writer/figure-spec — COHERENT
Tight: defines the four-block JSON spec, when to use it, how to render deterministically. Frontmatter excludes data plots ("Do not use for data plots → academic-plotting") and informal illustrations.
Evidence: "Spec is the source of truth; the rendered SVG / PDF is built from it and regenerates byte-stable from the same spec". Procedure stays inside that promise — no rendering pipeline detail beyond "tools/figure_renderer.py if present", no case-study examples.
No recommendation.

### writer/imported-paper-skill-catalog — COHERENT (slim by design)
A map/catalog skill. Structure section is a categorized list of external names; procedure is "translate to nearest local skill; if none, treat as task category". Voice stays catalog-style throughout — does not re-explain imported skills.
Evidence: "Do not assume those external `.codex/skills` files exist inside a MinionsOS project. Prefer local Writer skills". Pitfalls reinforce the catalog mode ("Creating a new local skill file to mirror every imported name").
No recommendation. The slim profile is right for what it does.

### writer/interactive-figure-prototype — COHERENT
Single trigger (3+ visual DOFs and no clear default), single artifact (`prototypes/<slug>.html`), explicit handoff back to static plotting.
Evidence: "Final submission still needs static, reproducible figure assets". Pitfall "Treating an interactive prototype as a submission artifact" closes the loop.
Lane vs `academic-plotting` and `figure-spec` is clean: prototype is exploration, the other two are final-asset disciplines.
No recommendation.

### writer/make-latex-model — COHERENT
Scaffolding skill. Single output (compilable empty skeleton), single trigger (start of paper / venue switch), explicit handoff to `paper-compile` ("Run `paper-compile` on the empty skeleton. Must produce a valid PDF with no undefined refs before any real content is added").
Evidence: "Minimal, compilable skeleton with the correct venue style". Body delivers exactly that — directory layout, citation wiring, preamble hygiene, compile gate.
No recommendation.

### writer/package-submission — COHERENT
Single bundle artifact (PDF + tex.zip + supplementary + code snapshot + venue checklist). Procedure starts with "re-compile from a clean state" via `paper-compile`, ends with venue-checklist gating.
Evidence: "A clean delivery package where every piece aligns: PDF matches source, source compiles standalone, supplementary matches main paper, code snapshot reproduces claimed results". Pitfalls are venue-specific ("Forgetting to strip author info on anonymous submissions"), no drift into compile mechanics.
No recommendation.

### writer/paper-compile — COHERENT
Compile cycle skill: `latexmk -C`, log-driven diagnosis, ≤3 attempts, submission-shape checks. Stays inside the compile loop.
Evidence: "Iterate at most 3 attempts; every attempt must change at least one concrete source line identified from the log". Pitfalls all attack the compile loop ("Suppressing warnings by editing the log-reading script instead of the source").
No recommendation.

### writer/paper-search-tools — NEEDS POLISH
The frontmatter sells this as a tool reference ("Use MinionsOS paper-search MCP tools"). The body partly delivers that — explicit tool list and fallbacks. But the procedure leans into how-to-search-the-literature advice ("Search with a claim in mind", "Separate paper classes", "Verify before citing", "Never fabricate BibTeX") that is more general literature discipline than tool guide.
Evidence — tool-guide voice: "Tool families from the `minionsos` MCP server: `search_arxiv`, `search_pubmed`, ...".
Evidence — drift into discipline essay: "Search with a claim in mind. Query for the method family, closest competitors, datasets, baselines, benchmarks, and factual claims needing citation support."
This is not stitched-together — both halves are about literature lookup — but the skill is doing two jobs (tool reference + search discipline) and reads slightly mixed. Either trim the procedure to "how to use these specific tools well" (input shaping, pagination, when to read vs skim, when to fall back to WebSearch) or rename the skill to `paper-literature-search` and keep both halves.
Recommendation: light polish, two paths
- A: keep slug, trim procedure to tool-usage tactics; move the broader search discipline (claim-first search, paper-class grouping, fabrication ban) into `imported-paper-skill-catalog`'s "literature-and-search" notes or a dedicated `literature-search-discipline.md`.
- B: rename to `paper-literature-search`, keep both halves but be explicit about that double role in the summary.

### writer/paper-work-boundaries — COHERENT
Boundary-map skill. Trigger and structure align ("Open whenever Writer is about to delegate paper work to a `paper-*` subagent"). The 10-row boundary map is the load-bearing piece; the "Procedure" reduces to slot selection plus a `Files Changed` audit. Voice is declarative throughout — does not drift into how to run any one slot.
Evidence: "All paper work stays under `branches/writer/paper/`. Template / reference directories such as `template/` or `branches/writer/template/` are read-only". The cross-slot rule ("Dispatch slot A first; pass A's output as read-only context to slot B; slot B writes the final artifact") is a boundary rule, not procedure for the slot itself. Good.
No recommendation.

### writer/prepare-rebuttal — COHERENT
Single trigger (rebuttal window opens), single output shape (response blocks under `branches/writer/paper/rebuttal/`). Issue-cluster table maps response types onto handling cleanly.
Evidence: "Group issues, classify response type, coordinate evidence gathering via EACN, draft concise blocks that do not promise what the team cannot deliver". Procedure follows that order.
Distinct from `apply-revisions` (which handles post-acceptance revision incorporation) and `abstract-writing` (which is paper-internal narrative).
No recommendation.

## Cross-skill issues

### end-to-end-paper-workflow delegation — clean
The composite orchestrator delegates by subagent slot, not by re-implementing sub-skills. Phases 1-3 dispatch `paper-evidence-analyst` and `paper-literature-citation-builder`; phase 4 explicitly defers to `paper-work-boundaries`; phase 7 dispatches `paper-qa-auditor`. No abstract content, no compile mechanics, no rebuttal logic leak in. The frontmatter `references` field signals downstream selection without forcing re-implementation. This is the pattern other clusters should imitate.

### citation-audit (writer) vs citation-authenticity-audit (ethics) — mild overlap, lanes implicit
Both files audit existence + metadata + context, both produce per-entry verdicts. The de-facto lane split:

- `writer/citation-audit` is a full sweep before submission, owned by Writer, output `CITATION_AUDIT.md`/`.json` under `branches/writer/paper/`, source-of-truth for "are our citations OK to ship".
- `ethics/citation-authenticity-audit` is a sampled (20–30 %) watchdog covering both Writer's `.bib` and Reviewer-cited prior work, output under `artifacts/ethics/flags/` and `artifacts/ethics/reports/`, escalates via EACN ping to the affected author Role.

These lanes work, but neither file says "the other one exists and covers the complementary surface". A future contributor could collapse them or duplicate them. Recommendation: add one cross-pointer line in each frontmatter / "When to invoke" — `writer/citation-audit` notes that Ethics independently samples, and `ethics/citation-authenticity-audit` notes that Writer owns the pre-submission full sweep. No structural change needed.

### figure cluster lanes — clean
- `academic-plotting` — data plots (numerical axes), matplotlib/seaborn, publication defaults.
- `figure-spec` — formal architecture / pipeline diagrams, JSON-spec source of truth, deterministic render.
- `interactive-figure-prototype` — exploration tool for multi-DOF figure decisions, HTML playground, static asset still required.

Each defers explicitly to the others (`academic-plotting` says boxes-and-arrows → `figure-spec`; `figure-spec` says data plots → `academic-plotting`; `interactive-figure-prototype` ends by handing back to static plotting). Lanes are well drawn.

### latex / compile / submission handoff — clean
- `make-latex-model` produces a compilable empty skeleton and explicitly gates on `paper-compile` succeeding before content writing.
- `paper-compile` owns the compile loop with a 3-attempt cap and submission-shape checks (page count, fonts, undefined refs).
- `package-submission` re-invokes `paper-compile` on a clean state and adds bundle assembly (tex.zip standalone-compile, supplementary, code snapshot, venue checklist).

No re-implementation across the three. Each calls the previous one rather than copying its logic. The handoff `make-latex-model → paper-compile → package-submission` is the cleanest chain in the cluster.

### abstract-writing / apply-revisions / prepare-rebuttal — distinct
- `abstract-writing` is paper-internal narrative discipline (six-rung ladder). Triggered by drafting or rewriting the abstract.
- `prepare-rebuttal` is reviewer-response packet construction. Triggered by rebuttal window opening.
- `apply-revisions` is post-decision incorporation of accepted reviewer changes into the manuscript. Triggered by Weak Accept / Borderline outcome or rebuttal acceptance.

No theme repetition. `apply-revisions` correctly explicitly bridges `prepare-rebuttal` → `package-submission`; `prepare-rebuttal` does not drift into how to incorporate revisions; `abstract-writing` is fully decoupled from the review loop.

## Summary

The writer cluster is in good shape relative to the 缝合怪 risk. Thirteen of fourteen skills are single-purpose, single-voice, with honest scope. The composite skill (`end-to-end-paper-workflow`) orchestrates rather than re-implements, which is the right discipline for a workflow file. Cross-skill lanes (figure trio, latex chain, review trio) are clean.

The two soft items worth a polish pass:
1. `paper-search-tools` reads as a tool reference grafted onto a search-discipline essay. Either trim or rename.
2. `citation-audit` (writer) and `citation-authenticity-audit` (ethics) need a one-line scope-split note in each so future contributors do not collapse or duplicate them.

Neither rises to STITCHED-TOGETHER. No skill needs a rewrite.
