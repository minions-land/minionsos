---
slug: package-submission
summary: Assemble the final camera-ready / submission bundle — clean PDF, standalone-compilable source archive, supplementary, reproducible code snapshot, venue-specific checklist.
layer: logical
tools:
version: 2
status: active
supersedes:
references: paper-compile, end-to-end-paper-workflow
provenance: human
---

# Skill — Package Submission

A clean delivery package where every piece aligns: PDF matches source, source compiles standalone, supplementary matches main paper, code snapshot reproduces claimed results.

## When to invoke

- Final camera-ready handoff.
- Original submission package just before upload.
- Artifact-evaluation submission (code snapshot emphasis).

## Structure

Deliverables:

- **Main PDF.** Built from a clean compile.
- **`tex.zip`.** Source archive: all `*.tex`, `*.bib`, style files (`.sty` / `.cls` per venue), `figures/*.pdf` (prefer vector), `figures/*.png` (raster-only). Excludes `build/` intermediates, `.aux` / `.log`, editor backups, hidden files.
- **Supplementary.** `supplementary.pdf` if venue separates it; main PDF references ("see Appendix A") resolve to the correct document.
- **Code snapshot.** `README` with exact reproduction commands, `requirements.txt` or lockfile, pointers to `artifacts/exp-{id}/` for each reported number, license. Paths and secrets scrubbed.

Venue checklist items: anonymous (no identifying self-citations), page limit, fonts embedded, file size.

## Procedure

1. **Re-compile from a clean state.** Delete `build/`, run `paper-compile` from scratch. Never ship a PDF whose source cannot rebuild it.
2. **Build `tex.zip`** per the Structure spec.
3. **Verify the archive compiles standalone.** Extract to a scratch directory on a clean path, run `latexmk -pdf main.tex`. Must produce the same PDF. No system-specific includes.
4. **Assemble supplementary.** Merge appendix-only content into `supplementary.pdf` if the venue separates it. Verify cross-document references resolve.
5. **Prepare the code snapshot.** `README` with exact reproduction commands, `requirements.txt` or equivalent, pointers to `artifacts/exp-{id}/` per reported number, license. Scrub paths and secrets.
6. **Run the venue checklist.** Anonymous (no author info or blinding-breaking self-citations); page limit (ML: body to Conclusion; IEEE: total including refs); fonts embedded (`pdffonts main.pdf | grep -v yes` empty); file size within venue limit (typically < 50 MB; prefer < 10 MB).
7. **Gate on readiness.** Do not mark the package ready while any checklist item is missing; list gaps explicitly.

Every reproducibility claim (e.g. "Table 3 reproduced") is marked `[derived: artifacts/exp-<id>/report.md]`.

## Pitfalls

- Shipping a PDF whose source does not compile on a clean machine.
- Forgetting to strip author info on anonymous submissions.
- Code snapshot that reproduces "something close" rather than the claimed numbers. If numbers do not match, fix the snapshot or honestly report the gap.
