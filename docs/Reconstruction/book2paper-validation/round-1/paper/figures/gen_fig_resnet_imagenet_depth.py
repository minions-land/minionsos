#!/usr/bin/env python
"""Figure: ResNet ImageNet top-1/top-5 val error vs. depth (Table 3, 10-crop).
Data: figures/data/resnet_imagenet_depth.csv <- evidence/tables/table3_imagenet_validation_full.md
ResNet-34 = option A; ResNet-50/101/152 = option B. Monotone decrease supports C03, C05.
"""
import csv, pathlib, subprocess, sys
import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt

# Font stack: Arial -> Helvetica -> DejaVu Sans -> Liberation Sans. Do NOT override per element.
mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"],
    "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
    "axes.spines.right": False, "axes.spines.top": False,
    "axes.linewidth": 0.8, "legend.frameon": False,
})
PALETTE = {"top1": "#0072B2", "top5": "#CC79A7"}

here = pathlib.Path(__file__).parent
rows = list(csv.DictReader(
    (ln for ln in (here / "data" / "resnet_imagenet_depth.csv").read_text().splitlines()
     if not ln.startswith("#"))))
depth = [int(r["depth"]) for r in rows]
top1 = [float(r["top1"]) for r in rows]
top5 = [float(r["top5"]) for r in rows]

fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(depth, top1, "-o", color=PALETTE["top1"], linewidth=1.8, markersize=6, label="top-1 error")
ax.plot(depth, top5, "-s", color=PALETTE["top5"], linewidth=1.8, markersize=6, label="top-5 error")
for d, y in zip(depth, top1):
    ax.annotate(f"{y:.2f}", (d, y), fontsize=8, xytext=(0, 6), textcoords="offset points", ha="center")
for d, y in zip(depth, top5):
    ax.annotate(f"{y:.2f}", (d, y), fontsize=8, xytext=(0, -12), textcoords="offset points", ha="center")
ax.set_xlabel("ResNet depth (layers)"); ax.set_ylabel("ImageNet val error (%, 10-crop)")
ax.set_xticks(depth); ax.set_xticklabels([str(d) for d in depth])
ax.tick_params(direction="out", length=2.2, width=0.6)
ax.legend(loc="upper right", fontsize=9)
fig.tight_layout()
out = here / "fig_resnet_imagenet_depth.pdf"
fig.savefig(out); fig.savefig(out.with_suffix(".png"), dpi=300)

res = subprocess.run(["pdffonts", str(out)], capture_output=True, text=True, check=False)
if "Type 3" in res.stdout:
    sys.stderr.write(f"FATAL: Type-3 fonts in {out}\n{res.stdout}\n"); sys.exit(2)
print(f"[fonttype-check] OK — {out}")
