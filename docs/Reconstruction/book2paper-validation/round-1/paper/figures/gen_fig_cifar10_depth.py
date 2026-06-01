#!/usr/bin/env python
"""Figure: CIFAR-10 test error vs. ResNet depth (Table 6, option A identity shortcuts).
Data: figures/data/cifar10_depth.csv <- evidence/tables/table6_cifar10.md
depth-110 = best of 5 runs (mean 6.61 +/- 0.16). Error falls 20->110 then rises at 1202
(overfitting, not optimization failure). Supports C06, C07.
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
PALETTE = {"line": "#0072B2", "over": "#D55E00", "black": "#272727"}

here = pathlib.Path(__file__).parent
rows = list(csv.DictReader(
    (ln for ln in (here / "data" / "cifar10_depth.csv").read_text().splitlines()
     if not ln.startswith("#"))))
depth = [int(r["depth"]) for r in rows]
err = [float(r["error"]) for r in rows]

fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(depth, err, "-o", color=PALETTE["line"], linewidth=1.8, markersize=6)
# highlight the 1202-layer overfitting point
ax.plot(depth[-1], err[-1], "o", color=PALETTE["over"], markersize=8)
for d, y in zip(depth, err):
    ax.annotate(f"{y:.2f}", (d, y), fontsize=8, xytext=(0, 7), textcoords="offset points", ha="center")
ax.annotate("overfits", (depth[-1], err[-1]), fontsize=8, color=PALETTE["over"],
            xytext=(-4, -16), textcoords="offset points", ha="center")
ax.set_xscale("log")
ax.set_xlabel("CIFAR-10 ResNet depth (layers, log scale)")
ax.set_ylabel("test error (%)")
ax.set_xticks(depth); ax.set_xticklabels([str(d) for d in depth])
ax.tick_params(direction="out", length=2.2, width=0.6)
fig.tight_layout()
out = here / "fig_cifar10_depth.pdf"
fig.savefig(out); fig.savefig(out.with_suffix(".png"), dpi=300)

res = subprocess.run(["pdffonts", str(out)], capture_output=True, text=True, check=False)
if "Type 3" in res.stdout:
    sys.stderr.write(f"FATAL: Type-3 fonts in {out}\n{res.stdout}\n"); sys.exit(2)
print(f"[fonttype-check] OK — {out}")
