"""Fig: CIFAR-10 test error vs ResNet depth (incl. 1202-layer overfitting point).
Source data: evidence/tables/table6_cifar10.md (EXACT). Params from same table.
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

# EXACT from Table 6 (CIFAR-10 test error %). 110 is the 5-run best (mean 6.61+-0.16).
depth = [20, 32, 44, 56, 110, 1202]
err = [8.75, 7.51, 7.17, 6.97, 6.43, 7.93]
PALETTE = {"line": "#0072B2", "over": "#D55E00"}

fig, ax = plt.subplots(figsize=(6, 4))
# split: monotone-improving 20..110, then the 1202 overfitting point.
ax.plot(depth[:5], err[:5], "-o", color=PALETTE["line"], lw=1.8, ms=6, label="ResNet (improves with depth)")
ax.plot([110, 1202], [6.43, 7.93], "--", color=PALETTE["over"], lw=1.4)
ax.plot([1202], [7.93], "D", color=PALETTE["over"], ms=7, label="ResNet-1202 (overfits)")
for d, y in zip(depth, err):
    dy = 7 if d != 1202 else 7
    ax.annotate(f"{y:.2f}", (d, y), fontsize=8, xytext=(0, dy), textcoords="offset points", ha="center")
ax.set_xscale("log")
ax.set_xlabel("CIFAR-10 ResNet depth (layers, log scale)")
ax.set_ylabel("Test error (%)")
ax.set_xticks(depth); ax.set_xticklabels([str(d) for d in depth])
ax.minorticks_off()
ax.set_ylim(6, 9.2)
ax.tick_params(direction="out", length=2.2, width=0.6)
ax.legend(loc="upper center", fontsize=9)
fig.tight_layout()
out = pathlib.Path(__file__).with_name("fig_cifar_depth.pdf")
fig.savefig(out); fig.savefig(out.with_suffix(".png"), dpi=300)
raw = out.read_bytes()
if re.search(rb"/Type3\b", raw):
    sys.stderr.write("FATAL: Type-3 font in figure.\n"); sys.exit(2)
print(f"[fonttype-check] OK {out.name}")
