export const meta = {
  name: 'book2paper-round',
  description: 'Validate Book→Paper on real data: generate a compilable LaTeX paper from the ResNet Book, then judge it against the ground-truth paper and synthesize a convergence verdict + concrete skill-improvement deltas.',
  phases: [
    { title: 'Generate', detail: 'one agent: Book → LaTeX → compiled paper.pdf' },
    { title: 'Judge', detail: '3 parallel judges compare generated vs ground-truth' },
    { title: 'Synthesize', detail: 'convergence verdict + writer-skill deltas' },
  ],
}

// The (Book, ground-truth) validation fixture is a local-only asset (a
// hand-built Book of the ResNet paper + its published PDF) and is NOT part of
// the delivered tree. Point at it via args/env when re-running this harness:
//   args.book_dir / MINIONS_B2P_BOOK   → the source Book directory
//   args.truth_pdf / MINIONS_B2P_TRUTH → the ground-truth paper PDF
const BOOK = (args && args.book_dir) || process.env.MINIONS_B2P_BOOK || ''
const TRUTH = (args && args.truth_pdf) || process.env.MINIONS_B2P_TRUTH || ''
const SKILL = '/Users/mjm/MinionsOS/minions/roles/common/skills/book-to-paper.md'
const SKILLS_DIR = '/Users/mjm/MinionsOS/minions/roles/common/skills'
const ROUND = (args && args.round_dir) || '/Users/mjm/MinionsOS/docs/Reconstruction/book2paper-validation/round-1'
const PAPER = ROUND + '/paper'

const GEN_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['compiled', 'pdf_path', 'pages', 'sections_written', 'tables_rendered', 'figures_rendered', 'coverage_report_path', 'notes'],
  properties: {
    compiled: { type: 'boolean', description: 'Did latexmk produce a paper.pdf?' },
    pdf_path: { type: 'string' },
    pages: { type: 'integer', description: 'Page count of generated PDF, -1 if not compiled.' },
    sections_written: { type: 'array', items: { type: 'string' }, description: 'Section names actually drafted, in order.' },
    tables_rendered: { type: 'integer' },
    figures_rendered: { type: 'integer' },
    coverage_report_path: { type: 'string', description: 'Path to book_to_paper_coverage.md (claim→Book id, number→evidence source, ungrounded sentences, omitted claims).' },
    notes: { type: 'string', description: 'What worked / what blocked (esp. compile errors hit and how resolved).' },
  },
}
// SCHEMAS-BELOW

const JUDGE_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['axis', 'score', 'findings', 'gap_vs_truth', 'skill_deltas'],
  properties: {
    axis: { type: 'string' },
    score: { type: 'integer', description: '1-5; 5 = generated matches ground-truth quality on this axis.' },
    findings: { type: 'array', items: { type: 'string' }, description: 'Concrete observations citing specific generated-vs-truth differences.' },
    gap_vs_truth: { type: 'string', description: 'The single biggest remaining gap on this axis.' },
    skill_deltas: { type: 'array', items: { type: 'string' }, description: 'Concrete edits to book-to-paper.md or a writer skill that would close the gap.' },
  },
}

const SYNTH_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['mean_score', 'converged', 'verdict', 'top_gaps', 'prioritized_skill_deltas', 'overclaim_flags'],
  properties: {
    mean_score: { type: 'number' },
    converged: { type: 'boolean', description: 'True only if quality is stable & high enough to land the skill (no critical gaps, no over-claim, compiles).' },
    verdict: { type: 'string', description: '2-4 sentences: is Book→Paper good enough to land, or what must improve.' },
    top_gaps: { type: 'array', items: { type: 'string' } },
    prioritized_skill_deltas: { type: 'array', items: { type: 'string' }, description: 'Ordered concrete skill edits for the next round.' },
    overclaim_flags: { type: 'array', items: { type: 'string' }, description: 'Any place the generated paper claimed more than the Book/ground-truth supports (must be empty to converge).' },
  },
}

phase('Generate')
const gen = await agent(
  `You are validating the Book→Paper capability END-TO-END (no human in the loop). ` +
  `Read the skill at ${SKILL} and the writer/latex/figure skills in ${SKILLS_DIR} ` +
  `(make-latex-model, paper-compile, abstract-writing, introduction-discipline, related-work-discipline, ` +
  `methodology-discipline, conclusion-limitation, latex-typography, academic-plotting, figure-spec, citation-audit). ` +
  `INPUT Book (the knowledge package): ${BOOK} — read Book.md/PAPER.md manifest, all logic/*, src/*, evidence/* (every table+figure has EXACT numbers), trace/exploration_tree.yaml. ` +
  `\n\nTASK: generate a compilable LaTeX paper from the Book into ${PAPER}/ following the skill's Book-layer→section map ` +
  `(abstract→introduction→related work→methodology→experiments→conclusion). Use make-latex-model to lay down main.tex+sections/*.tex+references.bib. ` +
  `Render the evidence tables with EXACT numbers from evidence/tables/* (never invent/round). Build references.bib from logic/related_work.md. ` +
  `Then compile: cd ${PAPER} && latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex 2>&1 | tee compile.log — fix small auto-fixable errors, ≤3 iterations. ` +
  `Write ${PAPER}/book_to_paper_coverage.md: every paper claim→its Book claim id, every number→its evidence/ source file, any ungrounded sentence (should be none), any Book claim omitted. ` +
  `\n\nHARD RULE: every sentence must trace to the Book — no over-claim beyond claims.md Statements, no invented numbers. ` +
  `This is a real toolchain (pdflatex/latexmk present). Produce a real paper.pdf. Report honestly if compile fails and why.`,
  { label: 'generate', phase: 'Generate', schema: GEN_SCHEMA },
)

phase('Judge')
const truthRef = `Ground-truth paper PDF: ${TRUTH} (read it — 12 pages, ResNet/He et al. 2015). Generated paper dir: ${PAPER} (paper.pdf + sections/*.tex + book_to_paper_coverage.md). Book the generated paper came from: ${BOOK}.`
const JUDGES = [
  { axis: 'Claim coverage & scope calibration', focus: 'Did the generated paper surface every headline claim from the Book/ground-truth (degradation problem, residual fixes it, depth gains to 152, identity-shortcut sufficiency, bottleneck, CIFAR/COCO transfer)? Crucially: does any generated sentence OVER-CLAIM beyond what the Book claims.md Statement + Evidence basis supports, vs the measured restraint of the real paper? Under-claim (dropped verified claims) too.' },
  { axis: 'Evidence fidelity', focus: 'Do the generated Experiments tables/numbers EXACTLY match the ground-truth (e.g. ResNet-34=25.03, ResNet-152 top-1=21.43, 3.57% ensemble top-5, COCO 28% rel)? Any invented/rounded/mismatched number is a critical finding. Check tables in evidence/ are faithfully rendered.' },
  { axis: 'Structure, section flow & typography', focus: 'Section order (abstract→intro→related→method→experiments→conclusion), narrative arc (problem→solution→evidence), did it compile to a real multi-page PDF, page count vs the 12-page truth, LaTeX/typography quality (overfull boxes, refs resolve, figures/tables placed). Compare flow against the real paper.' },
]
const judgments = await parallel(JUDGES.map((j) => () =>
  agent(
    `You are an adversarial reviewer comparing a MACHINE-GENERATED paper (from a Book) against the ground-truth published paper, on ONE axis: ${j.axis}. ${truthRef}\n\nFocus: ${j.focus}\n\nRead BOTH the generated sections and the ground-truth PDF. Be concrete and cite specific differences (quote a generated line vs the truth). Score 1-5 (5 = matches ground-truth quality). Do NOT be generous — the point is to find the gap so we can close it. Return concrete skill_deltas (edits to book-to-paper.md or a named writer skill).`,
    { label: 'judge:' + j.axis.split(' ')[0], phase: 'Judge', schema: JUDGE_SCHEMA },
  )
))

phase('Synthesize')
const synth = await agent(
  `You are the convergence judge for the Book→Paper validation. The generation result: ${JSON.stringify(gen)}. ` +
  `The three axis judgments: ${JSON.stringify(judgments.filter(Boolean))}. ` +
  `\n\nDecide whether the Book→Paper skill (book-to-paper.md + the writer skills) has CONVERGED — i.e. quality is high & stable enough to LAND the skill: it compiles, surfaces all headline claims, evidence numbers are exact, and there is NO over-claim beyond the Book. ` +
  `If not converged, give an ORDERED list of the most impactful concrete skill edits for the next round. List any over-claim flags (must be empty to converge). Be honest and non-overclaiming: base the verdict on the measured judgments, not optimism.`,
  { label: 'synthesize', phase: 'Synthesize', schema: SYNTH_SCHEMA },
)

return { generation: gen, judgments: judgments.filter(Boolean), synthesis: synth }

