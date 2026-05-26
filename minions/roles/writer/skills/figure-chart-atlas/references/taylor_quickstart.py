#!/usr/bin/env python3
# ruff: noqa: RUF001, RUF002, RUF003, I001
# σ (sigma) and θ (theta) are intentional math notation — Taylor diagrams
# are defined in terms of σ_m / σ_r and θ = arccos(R); ASCII substitution
# would defeat the documentation purpose. I001 is intentional too:
# matplotlib.use("Agg") must run before matplotlib.pyplot is imported.
"""Taylor diagram quick-start — demonstrates all three variants.

Usage:
    python taylor_quickstart.py

Outputs:
    - taylor_normalized.pdf (22 models, normalized σ)
    - taylor_standard.pdf (5 models, physical units)
    - taylor_extended.pdf (3 models with negative R)

Requirements:
    - matplotlib >= 3.9 (tested on 3.10.9)
    - numpy >= 1.20
    - pdffonts (poppler-utils) for Type-42 verification
"""

import subprocess
import sys

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib as mpl
import matplotlib.pyplot as plt
import mpl_toolkits.axisartist.floating_axes as fa
import mpl_toolkits.axisartist.grid_finder as gf
from matplotlib.projections import PolarAxes

# Non-skippable rcParams preamble (figure-chart-atlas discipline)
mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"],
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "axes.linewidth": 0.8,
        "legend.frameon": False,
    }
)


def taylor_diagram(
    fig, rect, ref_std, *, extend=False, normalized=False, srange=(0.0, 1.6), label="Reference"
):
    """Set up a Taylor-diagram axes and return (ax, polar_ax, ref_radius).

    Matplotlib 3.11-ready: uses apply_theta_transforms=False.
    """
    tr = PolarAxes.PolarTransform(apply_theta_transforms=False)
    rlocs = np.array([0, 0.2, 0.4, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99, 1])
    if extend:
        rlocs = np.concatenate([-rlocs[::-1], rlocs[1:]])
    tlocs = np.arccos(rlocs)
    gl1 = gf.FixedLocator(tlocs)
    tf1 = gf.DictFormatter(dict(zip(tlocs, [f"{x:.2g}" for x in rlocs], strict=True)))
    smin, smax = srange
    if not normalized:
        smin, smax = smin * ref_std, smax * ref_std
    ref_radius = 1.0 if normalized else ref_std
    ghelper = fa.GridHelperCurveLinear(
        tr,
        extremes=(0, np.pi if extend else np.pi / 2, smin, smax),
        grid_locator1=gl1,
        tick_formatter1=tf1,
    )
    ax = fa.FloatingSubplot(fig, rect, grid_helper=ghelper)
    fig.add_subplot(ax)
    ax.axis["top"].set_axis_direction("bottom")
    ax.axis["top"].toggle(ticklabels=True, label=True)
    ax.axis["top"].major_ticklabels.set_axis_direction("top")
    ax.axis["top"].label.set_axis_direction("top")
    ax.axis["top"].label.set_text("Correlation")
    ax.axis["left"].set_axis_direction("bottom")
    ax.axis["left"].label.set_text(
        "Normalized standard deviation" if normalized else "Standard deviation"
    )
    ax.axis["right"].set_axis_direction("top")
    ax.axis["right"].toggle(ticklabels=True)
    ax.axis["right"].major_ticklabels.set_axis_direction("bottom" if extend else "left")
    if extend:
        ax.axis["bottom"].toggle(ticklabels=False, label=False)
    else:
        ax.axis["bottom"].set_visible(False)
    polar_ax = ax.get_aux_axes(tr)
    polar_ax.plot([0], [ref_radius], "k*", ms=10, label=label)
    t = np.linspace(0, np.pi if extend else np.pi / 2)
    polar_ax.plot(t, np.full_like(t, ref_radius), "k--", lw=0.6, alpha=0.6)
    return ax, polar_ax, ref_radius


def add_rmsd_contours(polar_ax, ref_radius, levels=None, srange=(0.0, 1.6)):
    """Overlay centered-RMSD contours."""
    rs, ts = np.meshgrid(
        np.linspace(srange[0] * ref_radius, srange[1] * ref_radius, 200),
        np.linspace(0, np.pi, 200),
    )
    rms = np.sqrt(ref_radius**2 + rs**2 - 2 * ref_radius * rs * np.cos(ts))
    cs = polar_ax.contour(
        ts, rs, rms, levels=levels or 5, colors="0.5", linewidths=0.6, linestyles=":"
    )
    polar_ax.clabel(cs, inline=True, fontsize=7, fmt="%.2f")
    return cs


def verify_type42(pdf_path):
    """Check for Type-3 fonts and fail if found."""
    result = subprocess.run(["pdffonts", pdf_path], capture_output=True, text=True, check=False)
    if "Type 3" in result.stdout:
        sys.stderr.write(f"FATAL: {pdf_path} contains Type-3 bitmap fonts.\n{result.stdout}\n")
        sys.exit(2)
    print(f"✓ {pdf_path}: Type-42 fonts only")


def demo_normalized():
    """Variant 1: Normalized (22 models, radius = σ_m / σ_r)."""
    print("\n=== Variant 1: Normalized (22 models) ===")
    np.random.seed(0)
    n_models = 22
    ref = np.cumsum(np.random.randn(500))
    ref_std = ref.std(ddof=1)
    models = []
    for i in range(n_models):
        noise = np.random.randn(500) * (0.2 + 0.8 * np.random.rand())
        bias_corr = 0.5 + 0.5 * np.random.rand()
        models.append((f"M{i + 1:02d}", ref * bias_corr + noise))

    fig = plt.figure(figsize=(7, 6))
    _ax, pax, ref_r = taylor_diagram(fig, 111, ref_std, normalized=True, srange=(0.0, 1.6))
    add_rmsd_contours(pax, ref_r, levels=[0.25, 0.5, 0.75, 1.0, 1.25])

    cmap = plt.get_cmap("viridis")
    for i, (name, series) in enumerate(models):
        series_c = series - series.mean()
        ref_c = ref - ref.mean()
        sigma = series_c.std(ddof=1) / ref_std
        R = np.corrcoef(series_c, ref_c)[0, 1]
        pax.plot(np.arccos(R), sigma, "o", color=cmap(i / max(n_models - 1, 1)), ms=5, label=name)

    fig.legend(
        loc="center right",
        bbox_to_anchor=(1.0, 0.5),
        fontsize=7,
        ncol=1,
        handlelength=1.0,
        columnspacing=0.6,
    )
    fig.savefig("taylor_normalized.pdf", bbox_inches="tight")
    print("  Saved: taylor_normalized.pdf")
    verify_type42("taylor_normalized.pdf")


def demo_standard():
    """Variant 2: Standard (5 models, radius = σ in physical units)."""
    print("\n=== Variant 2: Standard (5 climate models, m/s) ===")
    np.random.seed(1)
    ref = np.cumsum(np.random.randn(1000)) * 0.5  # wind speed in m/s
    ref_std = ref.std(ddof=1)
    print(f"  Reference σ = {ref_std:.2f} m/s")

    models = [
        ("GCM-A", ref * 0.85 + np.random.randn(1000) * 0.3),
        ("GCM-B", ref * 0.92 + np.random.randn(1000) * 0.25),
        ("GCM-C", ref * 1.05 + np.random.randn(1000) * 0.4),
        ("GCM-D", ref * 0.78 + np.random.randn(1000) * 0.5),
        ("GCM-E", ref * 0.98 + np.random.randn(1000) * 0.2),
    ]

    fig = plt.figure(figsize=(6, 5))
    _ax, pax, ref_r = taylor_diagram(fig, 111, ref_std, normalized=False, srange=(0.5, 1.5))
    add_rmsd_contours(pax, ref_r, levels=[0.5, 1.0, 1.5, 2.0])

    colors = ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2"]
    for i, (name, series) in enumerate(models):
        series_c = series - series.mean()
        ref_c = ref - ref.mean()
        sigma = series_c.std(ddof=1)
        R = np.corrcoef(series_c, ref_c)[0, 1]
        pax.plot(np.arccos(R), sigma, "o", color=colors[i], ms=7, label=name)
        print(f"  {name}: σ={sigma:.2f} m/s, R={R:.3f}")

    fig.legend(loc="upper left", fontsize=8)
    fig.savefig("taylor_standard.pdf", bbox_inches="tight")
    print("  Saved: taylor_standard.pdf")
    verify_type42("taylor_standard.pdf")


def demo_extended():
    """Variant 3: Extended (3 models with negative R, θ ∈ [0, π])."""
    print("\n=== Variant 3: Extended (negative correlation) ===")
    np.random.seed(2)
    ref = np.cumsum(np.random.randn(800))
    ref_std = ref.std(ddof=1)

    # Model A: good match
    model_a = ref * 0.9 + np.random.randn(800) * 1.5
    # Model B: anti-correlated (inverted signal)
    model_b = -ref * 0.6 + np.random.randn(800) * 2.0
    # Model C: moderate match
    model_c = ref * 0.7 + np.random.randn(800) * 2.5

    models = [("Model-A", model_a), ("Model-B", model_b), ("Model-C", model_c)]

    fig = plt.figure(figsize=(7, 5))
    _ax, pax, ref_r = taylor_diagram(
        fig, 111, ref_std, normalized=True, extend=True, srange=(0.0, 1.8)
    )
    add_rmsd_contours(pax, ref_r, levels=[0.5, 1.0, 1.5, 2.0])

    colors = ["#4E79A7", "#E15759", "#76B7B2"]
    for i, (name, series) in enumerate(models):
        series_c = series - series.mean()
        ref_c = ref - ref.mean()
        sigma = series_c.std(ddof=1) / ref_std
        R = np.corrcoef(series_c, ref_c)[0, 1]
        pax.plot(np.arccos(R), sigma, "o", color=colors[i], ms=8, label=name)
        print(f"  {name}: σ/σ_ref={sigma:.2f}, R={R:.3f}, θ={np.arccos(R):.2f} rad")

    fig.legend(loc="upper right", fontsize=9)
    fig.savefig("taylor_extended.pdf", bbox_inches="tight")
    print("  Saved: taylor_extended.pdf")
    verify_type42("taylor_extended.pdf")


if __name__ == "__main__":
    print("Taylor Diagram Quick-Start (v2.0)")
    print("=" * 50)
    demo_normalized()
    demo_standard()
    demo_extended()
    print("\n" + "=" * 50)
    print("✓ All variants generated successfully")
    print("✓ Type-42 font compliance verified")
    print("\nNext steps:")
    print("  - Open PDFs to inspect visually")
    print("  - Adapt taylor_diagram() and add_rmsd_contours() for your data")
    print("  - See taylor-diagram.md for full discipline checklist")
