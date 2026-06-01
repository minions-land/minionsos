"""Fig: ResNet ImageNet depth scaling -- top-1/top-5 error (10-crop) vs depth.
Source data: evidence/tables/table3_imagenet_validation_full.md (EXACT).
Depth/FLOPs from evidence/tables/table1_imagenet_architectures.md.
Endpoint scatter -- not a trajectory.
"""
import sys, pathlib, re
import matplotlib as mpl
mpl.use("Agg")
mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"],
    "svg.fonttype": "none", "pdf.fonttype": 42, "ps.fonttype": 42,
    "axes.spines.right": False, "axes.spines.top": False,
    "axes.linewidth": 0.8, "legend.frameon": False,
})
import matplotlib.pyplot as plt

# EXACT from Table 3 (10-crop, ImageNet val). ResNet-34 is option B here.
depth = [34, 50, 101, 152]
top1 = [24.52, 22.85, 21.75, 21.43]
top5 = [7.46, 6.71, 6.05, 5.71]
PALETTE = {"top1": "#0072B2", "top5": "#D55E00"}

fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(depth, top1, "-o", color=PALETTE["top1"], lw=1.8, ms=6, label="top-1 error")
ax.plot(depth, top5, "-s", color=PALETTE["top5"], lw=1.8, ms=6, label="top-5 error")
for d, y in zip(depth, top1):
    ax.annotate(f"{y:.2f}", (d, y), fontsize=8, xytext=(0, 6), textcoords="offset points", ha="center")
for d, y in zip(depth, top5):
    ax.annotate(f"{y:.2f}", (d, y), fontsize=8, xytext=(0, -12), textcoords="offset points", ha="center")
ax.set_xlabel("ResNet depth (layers)")
ax.set_ylabel("ImageNet val. error (%, 10-crop)")
ax.set_xticks(depth)
ax.set_ylim(4, 26)
ax.tick_params(direction="out", length=2.2, width=0.6)
ax.legend(loc="center right", fontsize=9)
fig.tight_layout()
out = pathlib.Path(__file__).with_name("fig_imagenet_depth_scaling.pdf")
fig.savefig(out); fig.savefig(out.with_suffix(".png"), dpi=300)
raw = out.read_bytes()
if re.search(rb"/Type3\b", raw):
    sys.stderr.write("FATAL: Type-3 font in figure.\n"); sys.exit(2)
print(f"[fonttype-check] OK {out.name}")
