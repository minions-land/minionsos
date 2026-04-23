# Skill — Package Submission

Assemble the final camera-ready / submission bundle: PDF, source archive, supplementary, annotated code — coherent and complete.

## Core move

Produce a clean delivery package where every piece aligns with every other piece: the PDF matches the source, the source compiles standalone, the supplementary matches the main paper, and the code snapshot reproduces the claimed results.

## Procedure

1. **Re-compile from a clean state.** Delete `build/`, run `paper-compile` from scratch. The final PDF must come from a clean compile — never ship a PDF whose source cannot rebuild it.
2. **Build the source archive `tex.zip`.** Include: all `*.tex`, `*.bib`, style files (`.sty` / `.cls` as venue requires), `figures/*.pdf` (prefer vector), `figures/*.png` (for raster-only figures). Exclude: `build/` intermediates, `.aux` / `.log`, editor backups, hidden files.
3. **Verify the archive compiles standalone.** Extract to a scratch directory on a clean path, run `latexmk -pdf main.tex`. Must produce the same PDF as the submission. No relying on system-specific includes.
4. **Assemble supplementary.** Merge appendix-only content into `supplementary.pdf` if the venue separates it. Verify main PDF references (e.g. "see Appendix A") resolve to the correct document.
5. **Prepare the code snapshot.** Clean, commented, reproducible. Include: `README` with exact commands to reproduce headline results, `requirements.txt` or equivalent lockfile, pointers to `artifacts/exp-{id}/` for each reported number, license file. Scrub paths and secrets.
6. **Venue-specific checklist.**
   - Anonymous: no author names / affiliations / self-citations that break blinding.
   - Page limit: main body within rule (ML: to Conclusion end; IEEE: total incl. refs).
   - Fonts embedded: `pdffonts main.pdf | grep -v yes` empty.
   - File size within venue limit (typically < 50 MB; prefer < 10 MB).
7. **Gate on readiness.** Do not mark the package ready while any item in the checklist is missing; list gaps explicitly instead of silently shipping.

## When to invoke

- Final camera-ready handoff.
- Original submission package just before upload.
- Artifact-evaluation submission (code snapshot emphasis).

## Pitfalls

- Shipping a PDF whose source does not compile on a clean machine.
- Forgetting to strip author info on anonymous submissions.
- Code snapshot that reproduces "something close" rather than the claimed numbers. If numbers don't match, fix the snapshot or honestly report the gap.

## Output habit

Emit a readiness report: package contents list, checklist with pass/fail per item, remaining gaps if any, and paths to each deliverable. Every reproducibility claim (e.g. "Table 3 reproduced") is marked `[derived: artifacts/exp-<id>/report.md]` per root §9.
