"""Reference implementation: matplotlib-introspection visual audit.

Demonstrates how to implement the 7-row visual-format-check taxonomy at the
matplotlib object level (pre-rasterization). This complements the OpenCV-based
``visual_check.py`` which operates post-rasterization on pixel data.

Usage as a reference:
    Pass any rendered matplotlib Figure + dict of named Axes to
    ``audit_figure(fig, axes)`` and receive a list of DefectReport dicts.

Adapted from the ZheMa Proposal figure-audit script. The project-specific
figure builder has been removed; only the generic detection algorithms remain.

Dependencies: matplotlib (already a MinionsOS dev dependency).
"""

from __future__ import annotations

from typing import Any

PAD = 2.0  # px tolerance for overlap/overflow detection


def is_intentional_outside(text: Any) -> bool:
    """Anchor placed outside [0,1] in axes coords = explicit user choice."""
    try:
        tx, ty = text.get_position()
    except Exception:
        return False
    if text.get_transform() == text.axes.transAxes:
        return tx < 0 or tx > 1 or ty < 0 or ty > 1
    return False


def collect_all_text(ax: Any) -> list[tuple[str, Any]]:
    """Every visible text element in an axes."""
    items = []
    for t in ax.texts:
        if t.get_text().strip():
            items.append(("text", t))
    if ax.get_title() and ax.title.get_text().strip():
        items.append(("title", ax.title))
    if ax.xaxis.get_label().get_text().strip():
        items.append(("xlabel", ax.xaxis.get_label()))
    if ax.yaxis.get_label().get_text().strip():
        items.append(("ylabel", ax.yaxis.get_label()))
    for tk in ax.get_xticklabels() + ax.get_yticklabels():
        if tk.get_text().strip() and tk.get_visible():
            items.append(("tick", tk))
    return items


def detect_edge_overflow(fig: Any, axes: dict[str, Any]) -> list[dict[str, Any]]:
    """Detect text overflowing panel or figure boundaries (taxonomy rows 1-4)."""
    out: list[dict[str, Any]] = []
    fig_bbox = fig.bbox
    for label, ax in axes.items():
        ax_bbox = ax.get_window_extent()
        for kind, t in collect_all_text(ax):
            tb = t.get_window_extent()
            if kind in ("title", "xlabel", "ylabel", "tick"):
                for side, delta in [
                    ("left", fig_bbox.x0 - tb.x0),
                    ("right", tb.x1 - fig_bbox.x1),
                    ("bottom", fig_bbox.y0 - tb.y0),
                    ("top", tb.y1 - fig_bbox.y1),
                ]:
                    if delta > PAD:
                        out.append(
                            {
                                "defect_id": "edge_overflow",
                                "scope": "figure",
                                "panel": label,
                                "element": kind,
                                "side": side,
                                "overflow_px": round(delta, 1),
                                "text": t.get_text()[:80],
                            }
                        )
                continue
            if not is_intentional_outside(t):
                for side, delta in [
                    ("left", ax_bbox.x0 - tb.x0),
                    ("right", tb.x1 - ax_bbox.x1),
                    ("bottom", ax_bbox.y0 - tb.y0),
                    ("top", tb.y1 - ax_bbox.y1),
                ]:
                    if delta > PAD:
                        out.append(
                            {
                                "defect_id": "edge_overflow",
                                "scope": "panel",
                                "panel": label,
                                "element": kind,
                                "side": side,
                                "overflow_px": round(delta, 1),
                                "text": t.get_text()[:80],
                            }
                        )
            for side, delta in [
                ("left", fig_bbox.x0 - tb.x0),
                ("right", tb.x1 - fig_bbox.x1),
                ("bottom", fig_bbox.y0 - tb.y0),
                ("top", tb.y1 - fig_bbox.y1),
            ]:
                if delta > PAD:
                    out.append(
                        {
                            "defect_id": "edge_overflow",
                            "scope": "figure",
                            "panel": label,
                            "element": kind,
                            "side": side,
                            "overflow_px": round(delta, 1),
                            "text": t.get_text()[:80],
                        }
                    )
    return out


def detect_inter_panel_collision(fig: Any, axes: dict[str, Any]) -> list[dict[str, Any]]:
    """Detect text from one panel overlapping another panel's bbox (row 5)."""
    out: list[dict[str, Any]] = []
    panel_bboxes = {label: ax.get_window_extent() for label, ax in axes.items()}
    panel_images = {
        label: [im.get_window_extent() for im in ax.images] for label, ax in axes.items()
    }
    for label, ax in axes.items():
        for kind, t in collect_all_text(ax):
            tb = t.get_window_extent()
            for other_label, other_bb in panel_bboxes.items():
                if other_label == label:
                    continue
                if tb.x1 <= other_bb.x0 + PAD or other_bb.x1 <= tb.x0 + PAD:
                    continue
                if tb.y1 <= other_bb.y0 + PAD or other_bb.y1 <= tb.y0 + PAD:
                    continue
                out.append(
                    {
                        "defect_id": "inter_panel_collision",
                        "panel": label,
                        "element": kind,
                        "other_panel": other_label,
                        "text": t.get_text()[:80],
                    }
                )
    for ft in fig.texts:
        if not ft.get_text().strip():
            continue
        ftb = ft.get_window_extent()
        for label, panel_bb in panel_bboxes.items():
            if ftb.x1 <= panel_bb.x0 + PAD or panel_bb.x1 <= ftb.x0 + PAD:
                continue
            if ftb.y1 <= panel_bb.y0 + PAD or panel_bb.y1 <= ftb.y0 + PAD:
                continue
            out.append(
                {
                    "defect_id": "inter_panel_collision",
                    "panel": "fig",
                    "element": "fig.text",
                    "other_panel": label,
                    "text": ft.get_text()[:80],
                }
            )
    for label, ax in axes.items():
        for kind, t in collect_all_text(ax):
            tb = t.get_window_extent()
            for other_label, im_bbs in panel_images.items():
                if other_label == label:
                    continue
                for im_bb in im_bbs:
                    if tb.x1 <= im_bb.x0 + PAD or im_bb.x1 <= tb.x0 + PAD:
                        continue
                    if tb.y1 <= im_bb.y0 + PAD or im_bb.y1 <= tb.y0 + PAD:
                        continue
                    out.append(
                        {
                            "defect_id": "text_over_image",
                            "panel": label,
                            "element": kind,
                            "image_panel": other_label,
                            "text": t.get_text()[:80],
                        }
                    )
    return out


def detect_text_overlap(axes: dict[str, Any]) -> list[dict[str, Any]]:
    """Detect overlapping text within the same panel (row 6)."""
    out: list[dict[str, Any]] = []
    for label, ax in axes.items():
        items = [(kind, t, t.get_window_extent()) for kind, t in collect_all_text(ax)]
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                k1, t1, b1 = items[i]
                k2, t2, b2 = items[j]
                if b1.x1 <= b2.x0 + PAD or b2.x1 <= b1.x0 + PAD:
                    continue
                if b1.y1 <= b2.y0 + PAD or b2.y1 <= b1.y0 + PAD:
                    continue
                out.append(
                    {
                        "defect_id": "text_overlap",
                        "scope": "panel",
                        "panel": label,
                        "text_a": f"[{k1}] {t1.get_text()[:60]}",
                        "text_b": f"[{k2}] {t2.get_text()[:60]}",
                    }
                )
    return out


def audit_figure(fig: Any, axes: dict[str, Any]) -> list[dict[str, Any]]:
    """Run all detectors on a rendered matplotlib figure.

    Call ``fig.canvas.draw()`` before passing the figure — bounding boxes
    are only valid after the layout engine has run.

    Returns a flat list of defect dicts, each with at minimum:
      defect_id, panel, element, text (or text_a/text_b for overlaps).
    """
    return (
        detect_edge_overflow(fig, axes)
        + detect_text_overlap(axes)
        + detect_inter_panel_collision(fig, axes)
    )
