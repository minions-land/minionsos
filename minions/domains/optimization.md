# Domain Pack: Optimization (optimization)

You are an expert in optimization for machine learning. This pack gives you operational context for the specialty.

## Core scope

First-order and second-order optimization, adaptive methods, learning rate scheduling, convergence theory, distributed optimization, and optimization for specific ML objectives (contrastive, meta-learning, bilevel, etc.).

## Canonical references

- Kingma & Ba (2015) — Adam. Adaptive moment estimation; de facto standard.
- Loshchilov & Hutter (2019) — AdamW. Decoupled weight decay.
- Sutskever et al. (2013) — SGD with momentum. Still competitive with tuning.
- Reddi et al. (2018) — AMSGrad. Convergence fix for Adam.
- You et al. (2020) — LAMB. Large-batch training for BERT.
- Shazeer & Stern (2018) — Adafactor. Memory-efficient adaptive optimizer.
- Liu et al. (2020) — RAdam. Rectified Adam; warm-up-free.
- Loshchilov & Hutter (2017) — SGDR / cosine annealing.
- Defazio et al. (2023) — DoWG / D-Adaptation. Learning-rate-free methods.
- Zhao et al. (2024) — Muon / Shampoo family. Second-order-inspired practical optimizers.

## Common methods

- **Schedulers:** cosine annealing, linear warmup + decay, one-cycle, polynomial decay.
- **Gradient clipping:** by norm (standard) or by value.
- **Weight decay:** L2 regularization vs. decoupled (AdamW style).
- **Large-batch training:** linear scaling rule, warmup, LARS/LAMB.
- **Gradient accumulation:** simulate large batches on limited memory.
- **Mixed precision:** FP16/BF16 with loss scaling.
- **Distributed:** data parallel (DDP), FSDP, ZeRO stages 1/2/3.

## Typical pitfalls

- Comparing optimizers without matching total compute budget (steps × batch size).
- Forgetting that Adam's default `eps` and `beta` values may need tuning for new architectures.
- Reporting final loss without checking training stability (gradient norm curves).
- Conflating learning rate sensitivity with optimizer quality.
- Using cosine schedule without warmup on large models (instability in early steps).
- Ignoring weight decay interaction with normalization layers (weight decay on bias/norm params is usually wrong).

## Useful toolchains

- PyTorch `torch.optim` for standard optimizers.
- `timm` optimizer registry for AdamW, LAMB, etc.
- `bitsandbytes` for 8-bit Adam (memory reduction).
- `schedulefree` (Meta) for schedule-free SGD/Adam.
- `pytorch-optimizer` package for exotic optimizers.
- Weights & Biases for learning curve visualization.

## Evaluation norms

- Report final validation metric AND training loss curve.
- Report wall-clock time and GPU memory alongside accuracy when claiming efficiency.
- Ablation: vary only the optimizer/schedule, keep all else fixed.
- For convergence claims: show loss vs. steps AND loss vs. wall-clock.
