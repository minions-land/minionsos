# Skill — Paper Compile

Compile the LaTeX paper cleanly, fix the handful of errors that actually matter, and verify the output is submission-shaped.

## Core move

Run `latexmk` end-to-end, read `compile.log` carefully, auto-fix the small, safe class of errors (missing packages, broken refs, stale paths), and escalate anything that requires scientific judgment.

## Procedure

1. **Verify prerequisites.** `which pdflatex latexmk bibtex`. Ensure `workspace/paper/main.tex`, `*.bib`, `sections/`, and `figures/` exist. Fail fast with a clear error if not.
2. **Clean build.** In `workspace/paper/`: `latexmk -C` then `latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex 2>&1 | tee compile.log`.
3. **Diagnose from the log, not from guesses.** Common auto-fixable errors: missing `.sty` (install or remove), undefined `\ref`/`\cite` (fix label/key), missing figure files (check extension), BibTeX syntax nits. Do **not** silently delete user content to make errors disappear.
4. **Iterate at most 3 attempts.** Each attempt must change at least one concrete source line identified from the log; no blind recompiles.
5. **Scan for overfull hboxes** (`grep "Overfull \\\\hbox" compile.log`). Fix table / equation overflows per `SYSTEM.md` table layout rules (`\resizebox`, orientation pivot, `\small`). Minor paragraph overflows (<5pt) may be ignored.
6. **Detect stale section files.** For every `sections/*.tex`, grep `main.tex` for its basename; warn on any unreferenced file.
7. **Post-compile checks.** PDF exists and > 100KB; no `??` or `[?]` in output; page count within venue limit (ML venues: main body to end of Conclusion; IEEE: total including refs); fonts embedded (`pdffonts main.pdf | grep -v yes` is empty).

## When to invoke

- Before handing a draft to Reviewer or Expert for feedback.
- Before any camera-ready package.
- Whenever `[VERIFY]` markers, `?` refs, or overfull warnings are suspected.

## Pitfalls

- Suppressing warnings by editing the log-reading script instead of the source. The warnings are the point.
- Auto-deleting `\usepackage` lines to clear errors — often removes load-bearing macros.
- Counting pages including references on a venue that excludes them (or vice versa). Re-check the venue rule.

## Output habit

Emit a compact compilation report: status, PDF path, page count (main / refs / appendix), errors fixed (with line refs), warnings remaining, undefined refs / citations counts. Keep `compile.log` on disk. Mark page-count claims `[derived: pdfinfo @ <ts>]` per root §9.
