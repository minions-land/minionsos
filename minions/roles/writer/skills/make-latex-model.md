# Skill — Make LaTeX Model

Scaffold a clean LaTeX paper project under `workspace/paper/` matching the target venue's style.

## Core move

Produce a minimal, compilable paper skeleton with the correct venue style, a section layout matching the venue's expected structure, and the conventions `paper-compile` and `citation-audit` rely on — ready for Writer to fill in prose.

## Procedure

1. **Identify the venue.** Confirm the target (ICLR / NeurIPS / ICML / CVPR / ACL / AAAI / IEEE journal / IEEE conf). Fetch the official style file from the venue page; do not reuse an old copy without checking the year.
2. **Create the layout** under `workspace/paper/`:
   ```
   main.tex  sections/  figures/  tables/  references/  notes/  build/
   ```
   `main.tex` is the only entry point; sections are `\input{sections/NN_<name>.tex}` files, two-digit prefixed so lexical order = document order.
3. **Seed sections** matching venue norms: abstract, introduction, related work, method, experiments, conclusion, (ethics / reproducibility / limitations where required). Each section file starts with a `% [VERIFY]` marker list of outstanding claims.
4. **Wire citations.** Pick the citation command matching venue: `natbib` (`\citep` / `\citet`) for ML/NLP/CV venues; numeric `\cite{}` for IEEE. Create `references/references.bib`.
5. **Add preamble hygiene.** `\usepackage{cleveref}` + `\crefname` for custom theorem envs; `hyperref` loaded last; `microtype`; `booktabs` for tables. Ensure the style file's own conventions (font, margins) are not overridden.
6. **Verify compile.** Run `paper-compile` on the empty skeleton. It must produce a valid PDF with no undefined refs before any real content is added.

## When to invoke

- At the start of a paper-writing phase, before any section drafting.
- When switching venue (re-scaffold; do not patch the old one).

## Pitfalls

- Copy-pasting last year's style file. Venue rules drift; always pull the current one.
- Mixing citation styles (`\citep` in one section, `\cite` in another). Pick one per venue and lock it.
- Letting `main.tex` grow beyond preamble + `\input` lines. Content belongs in `sections/`.

## Output habit

Announce on EACN: the venue, the style file version/source, the section layout, and that the empty skeleton compiles. Mark `[derived: venue page <URL> @ <ts>]` for venue facts per root §9.
