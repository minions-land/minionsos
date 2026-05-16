# Submission Checklist

Standard checklist that must accompany every paper submission to Reviewer. Reviewer uses this as a gate: incomplete required items → immediate rejection without reading the manuscript.

## Required (all must be checked ✓)

- [ ] Problem statement: clearly defined research problem with motivation
- [ ] Literature survey: relevant prior work cited (≥10 references for a standard ML paper)
- [ ] Main experiment: quantitative results with clear metrics
- [ ] Baseline comparison: at least one established baseline with head-to-head numbers
- [ ] Ablation study: at least one ablation isolating a key design choice
- [ ] Case visualization: qualitative examples demonstrating behavior
- [ ] Mathematical formulation: formal problem setup or proof (if contribution is algorithmic/theoretical)

## Strongly recommended (missing items require brief justification)

- [ ] SOTA baseline comparison
- [ ] Hyperparameter sensitivity analysis
- [ ] Cross-dataset or cross-domain validation
- [ ] Reproducibility details (seeds, hardware, training time, hyperparameter table)
- [ ] Failure cases or limitations discussion

## Submission format

When submitting to Reviewer via EACN, attach this checklist as a structured block at the top of the submission message:

```
[SUBMISSION CHECKLIST]
- [✓] Problem statement
- [✓] Literature survey (N references)
- [✓] Main experiment (metrics: ...)
- [✓] Baseline comparison (against: ...)
- [✓] Ablation study (varying: ...)
- [✓] Case visualization
- [✓] Mathematical formulation
- [✗] SOTA comparison — justification: pending GPU allocation
[/SUBMISSION CHECKLIST]
```

Reviewer will reject without review if any Required item shows ✗.
