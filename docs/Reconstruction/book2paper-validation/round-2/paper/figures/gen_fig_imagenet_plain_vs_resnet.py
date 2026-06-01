"""Fig: ImageNet top-1 validation error (10-crop), plain vs ResNet at 18/34 layers.
Source data: evidence/tables/table2_imagenet_plain_vs_residual.md (EXACT numbers).
Endpoint bars only -- the Book does not tabulate per-iteration curves (Fig. 4).
"""
import subprocess, sys, pathlib
import matplotlib as mpl
mpl.use("Agg")
mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"],
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "axes.spines.right": False,
    "axes.spines.top": False,
    "axes.linewidth": 0.8,
    "legend.frameon": False,
})
import matplotlib.pyplot as plt
import numpy as np

# EXACT from Table 2 (top-1 %, 10-crop, ImageNet val).
depths = ["18 layers", "34 layers"]
plain = [27.94, 28.54]
resnet = [27.88, 25.03]
PALETTE = {"plain": "#767676", "resnet": "#0072B2"}

x = np.arange(len(depths))
w = 0.36
fig, ax = plt.subplots(figsize=(6, 4))
b1 = ax.bar(x - w/2, plain, w, label="plain", color=PALETTE["plain"])
b2 = ax.bar(x + w/2, resnet, w, label="ResNet", color=PALETTE["resnet"])
for bars in (b1, b2):
    for r in bars:
        ax.annotate(f"{r.get_height():.2f}", (r.get_x()+r.get_width()/2, r.get_height()),
                    ha="center", va="bottom", fontsize=8, xytext=(0, 1),
                    textcoords="offset points")
ax.set_xticks(x); ax.set_xticklabels(depths)
ax.set_ylabel("Top-1 error (%, 10-crop)")
ax.set_ylim(24, 29.5)
ax.tick_params(direction="out", length=2.2, width=0.6)
ax.legend(loc="upper left", fontsize=9)
fig.tight_layout()
out = pathlib.Path(__file__).with_name("fig_imagenet_plain_vs_resnet.pdf")
fig.savefig(out); fig.savefig(out.with_suffix(".png"), dpi=300)

raw = out.read_bytes()
import re
if re.search(rb"/Subtype\s*/Type3\b", raw) or re.search(rb"/Type3\b", raw):
    sys.stderr.write("FATAL: Type-3 font in figure.\n"); sys.exit(2)
print(f"[fonttype-check] OK {out.name}")
