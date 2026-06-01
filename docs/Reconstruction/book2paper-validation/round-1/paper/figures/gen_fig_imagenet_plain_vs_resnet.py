#!/usr/bin/env python
"""Figure: ImageNet plain vs. ResNet at 18/34 layers (Table 2, 10-crop top-1 val error).
Data: figures/data/imagenet_plain_vs_resnet.csv  <- evidence/tables/table2_imagenet_plain_vs_residual.md
Shows the degradation problem (plain-34 > plain-18) reversed by residual learning. Supports C01, C02.
"""
import csv, pathlib, subprocess, sys
import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Font stack: Arial -> Helvetica -> DejaVu Sans -> Liberation Sans. Do NOT override per element.
mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"],
    "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
    "axes.spines.right": False, "axes.spines.top": False,
    "axes.linewidth": 0.8, "legend.frameon": False,
})
PALETTE = {"plain": "#D55E00", "resnet": "#0072B2", "black": "#272727"}

here = pathlib.Path(__file__).parent
rows = list(csv.DictReader(
    (ln for ln in (here / "data" / "imagenet_plain_vs_resnet.csv").read_text().splitlines()
     if not ln.startswith("#"))))
depths = [r["depth"] for r in rows]
plain = [float(r["plain"]) for r in rows]
resnet = [float(r["resnet"]) for r in rows]

x = np.arange(len(depths)); w = 0.36
fig, ax = plt.subplots(figsize=(6, 4))
b1 = ax.bar(x - w / 2, plain, w, label="plain", color=PALETTE["plain"])
b2 = ax.bar(x + w / 2, resnet, w, label="ResNet", color=PALETTE["resnet"])
for bars in (b1, b2):
    for rect in bars:
        ax.annotate(f"{rect.get_height():.2f}", (rect.get_x() + rect.get_width() / 2, rect.get_height()),
                    ha="center", va="bottom", fontsize=8, xytext=(0, 1), textcoords="offset points")
ax.set_xticks(x); ax.set_xticklabels([f"{d}-layer" for d in depths])
ax.set_ylabel("top-1 error (%, 10-crop)"); ax.set_ylim(24, 29.5)
ax.tick_params(direction="out", length=2.2, width=0.6)
ax.legend(loc="upper left", fontsize=9)
fig.tight_layout()
out = here / "fig_imagenet_plain_vs_resnet.pdf"
fig.savefig(out); fig.savefig(out.with_suffix(".png"), dpi=300)

res = subprocess.run(["pdffonts", str(out)], capture_output=True, text=True, check=False)
if "Type 3" in res.stdout:
    sys.stderr.write(f"FATAL: Type-3 fonts in {out}\n{res.stdout}\n"); sys.exit(2)
print(f"[fonttype-check] OK — {out}")
