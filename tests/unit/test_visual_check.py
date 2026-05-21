"""Unit tests for minions.tools.visual_check.

Tests use synthetic NumPy / PIL images so the detector logic can be exercised
without rendering real PDFs. Each detector gets a positive and a negative
fixture; the orchestrators (``inspect_page`` / ``inspect_image``) get a smoke
test to confirm the auto-kind heuristic and report shape.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from minions.tools import visual_check as vc

# ---------------------------------------------------------------------------
# Fixtures — synthetic page builders
# ---------------------------------------------------------------------------


def _save_gray(arr: np.ndarray, path: Path) -> Path:
    """Save a uint8 grayscale array as RGB PNG (cv2 reads BGR by default)."""
    rgb = np.stack([arr, arr, arr], axis=-1).astype(np.uint8)
    Image.fromarray(rgb, mode="RGB").save(path)
    return path


def _two_column_page(
    h: int = 2200,
    w: int = 1700,
    left_fill: bool = True,
    right_fill: bool = True,
    left_void_band: tuple[int, int] | None = None,
    right_void_band: tuple[int, int] | None = None,
    bottom_blank_px: int = 0,
    margin_overflow: bool = False,
) -> np.ndarray:
    """Build a 2200x1700 fake page: white background, gray text rows in two cols."""
    page = np.full((h, w), 255, dtype=np.uint8)
    gx = w // 2
    gutter_w = 60
    margin_x = 80
    # Synthetic text rows: 5px ink + 13px gap.
    row_step = 18
    line_h = 5

    def fill_column(x0: int, x1: int, void: tuple[int, int] | None) -> None:
        for y in range(80, h - bottom_blank_px - 100, row_step):
            if void and void[0] <= y <= void[1]:
                continue
            page[y : y + line_h, x0:x1] = 60

    if left_fill:
        fill_column(margin_x, gx - gutter_w // 2, left_void_band)
    if right_fill:
        fill_column(gx + gutter_w // 2, w - margin_x, right_void_band)
    if margin_overflow:
        # Push dark pixels into the right margin band.
        page[200:600, w - 12 : w - 2] = 30
    return page


def _single_figure_image(h: int = 600, w: int = 800, edge_overflow: bool = False) -> np.ndarray:
    """Single-figure raster — small canvas, no double-column structure."""
    img = np.full((h, w), 255, dtype=np.uint8)
    # A fake plot blob in the centre.
    img[120:480, 120:680] = 220
    img[200:460, 200:660] = 90
    if edge_overflow:
        img[h - 15 : h - 2, :] = 25
    return img


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


def test_layout_rules_smooth_rows_forced_odd() -> None:
    rules = vc.LayoutRules(smooth_rows=8)
    assert rules.smooth_rows == 9


def test_defect_report_critical_or_major_filter() -> None:
    page = vc.PageReport(
        page=1,
        image_path="x",
        width=100,
        height=100,
        kind="layout",
        is_double_column=False,
        defects=[
            vc.Defect(defect_id="short_line", severity="minor", page=1, description="x"),
            vc.Defect(defect_id="column_void", severity="critical", page=1, description="y"),
        ],
    )
    report = vc.DefectReport(source_path="x", source_kind="image", page_count=1, pages=[page])
    out = report.critical_or_major_defects()
    assert len(out) == 1
    assert out[0].defect_id == "column_void"


# ---------------------------------------------------------------------------
# Detector — column_void
# ---------------------------------------------------------------------------


def test_column_void_detected_in_left_column() -> None:
    page = _two_column_page(left_void_band=(700, 1500))
    rules = vc.LayoutRules()
    defects = vc.detect_column_void(page, page=3, rules=rules)
    assert any(d.defect_id == "column_void" for d in defects)
    assert any("left" in d.location for d in defects)


def test_column_void_skipped_when_single_column() -> None:
    # Single full-width text page — gutter heuristic should fail.
    page = np.full((2200, 1000), 255, dtype=np.uint8)
    for y in range(80, 2100, 18):
        page[y : y + 5, 80:920] = 60
    rules = vc.LayoutRules()
    assert vc.detect_column_void(page, page=1, rules=rules) == []


def test_column_void_clean_two_column_no_defect() -> None:
    page = _two_column_page()
    assert vc.detect_column_void(page, page=1, rules=vc.LayoutRules()) == []


# ---------------------------------------------------------------------------
# Detector — trailing_whitespace
# ---------------------------------------------------------------------------


def test_trailing_whitespace_detected_on_short_last_page() -> None:
    page = _two_column_page(bottom_blank_px=1500)
    defects = vc.detect_trailing_whitespace(page, page=9, rules=vc.LayoutRules())
    assert any(d.defect_id == "trailing_whitespace" for d in defects)
    assert defects[0].metrics["trailing_ratio"] > 0.20


def test_trailing_whitespace_clean_full_page() -> None:
    page = _two_column_page(bottom_blank_px=0)
    assert vc.detect_trailing_whitespace(page, page=1, rules=vc.LayoutRules()) == []


# ---------------------------------------------------------------------------
# Detector — edge_overflow
# ---------------------------------------------------------------------------


def test_edge_overflow_right_margin_fires() -> None:
    page = _two_column_page(margin_overflow=True)
    defects = vc.detect_overflow_at_margins(page, page=2, rules=vc.LayoutRules())
    assert any(d.defect_id == "edge_overflow" and d.location == "right margin" for d in defects)


def test_edge_overflow_clean_page() -> None:
    page = _two_column_page(margin_overflow=False)
    assert vc.detect_overflow_at_margins(page, page=1, rules=vc.LayoutRules()) == []


# ---------------------------------------------------------------------------
# Detector — column_imbalance
# ---------------------------------------------------------------------------


def test_column_imbalance_fires_when_one_column_short() -> None:
    page = _two_column_page(right_void_band=(800, 2050))
    defects = vc.detect_column_imbalance(page, page=11, rules=vc.LayoutRules())
    assert any(d.defect_id == "column_imbalance" for d in defects)


def test_column_imbalance_clean() -> None:
    page = _two_column_page()
    assert vc.detect_column_imbalance(page, page=1, rules=vc.LayoutRules()) == []


# ---------------------------------------------------------------------------
# Detector — float_clustering
# ---------------------------------------------------------------------------


def test_float_clustering_two_adjacent_blocks() -> None:
    page = np.full((2200, 1700), 255, dtype=np.uint8)
    # Two solid dark blocks separated by 40 px (< default 100 px threshold).
    page[300:700, 200:1500] = 50
    page[740:1100, 200:1500] = 50
    defects = vc.detect_float_clustering(page, page=1, rules=vc.LayoutRules())
    assert any(d.defect_id == "float_clustering" for d in defects)


def test_float_clustering_well_spaced_no_defect() -> None:
    page = np.full((2200, 1700), 255, dtype=np.uint8)
    page[300:700, 200:1500] = 50
    page[1200:1600, 200:1500] = 50  # 500 px gap
    assert vc.detect_float_clustering(page, page=1, rules=vc.LayoutRules()) == []


# ---------------------------------------------------------------------------
# Detector — short_line
# ---------------------------------------------------------------------------


def test_short_line_in_single_column_page() -> None:
    page = np.full((1200, 800), 255, dtype=np.uint8)
    # Several full-width rows...
    for y in range(80, 1000, 18):
        page[y : y + 5, 80:720] = 60
    # ...then a short trailing band.
    page[1020:1040, 80:200] = 60
    defects = vc.detect_short_lines(page, page=1, rules=vc.LayoutRules())
    assert any(d.defect_id == "short_line" for d in defects)


# ---------------------------------------------------------------------------
# Orchestrator smoke tests
# ---------------------------------------------------------------------------


def test_inspect_page_layout_kind_auto_detects_double_column(tmp_path: Path) -> None:
    page = _two_column_page(left_void_band=(700, 1500))
    img = _save_gray(page, tmp_path / "page_001.png")
    report = vc.inspect_page(img, page=1, kind="auto")
    assert report.kind == "layout"
    assert report.is_double_column is True
    assert any(d.defect_id == "column_void" for d in report.defects)


def test_inspect_page_figure_kind_auto_for_small_image(tmp_path: Path) -> None:
    img_arr = _single_figure_image(edge_overflow=True)
    img = _save_gray(img_arr, tmp_path / "fig_main.png")
    report = vc.inspect_page(img, page=1, kind="auto")
    assert report.kind == "figure"
    assert report.is_double_column is False
    assert any(d.defect_id == "edge_overflow" for d in report.defects)


def test_inspect_page_missing_image_raises(tmp_path: Path) -> None:
    with pytest.raises(vc.VisualCheckError):
        vc.inspect_page(tmp_path / "does-not-exist.png")


def test_inspect_image_aggregates_summary(tmp_path: Path) -> None:
    img_arr = _single_figure_image(edge_overflow=True)
    img = _save_gray(img_arr, tmp_path / "fig.png")
    report = vc.inspect_image(img, kind="figure")
    assert report.source_kind == "image"
    assert report.page_count == 1
    assert report.summary.get("edge_overflow", 0) >= 1


def test_render_pdf_to_pages_missing_pdf_raises(tmp_path: Path) -> None:
    with pytest.raises(vc.VisualCheckError):
        vc.render_pdf_to_pages(tmp_path / "nope.pdf", tmp_path / "out", dpi=120)


def test_inspect_page_explicit_kind_overrides_auto(tmp_path: Path) -> None:
    page = _two_column_page()
    img = _save_gray(page, tmp_path / "p.png")
    # Force figure mode on a layout-shaped page; only edge_overflow should run.
    report = vc.inspect_page(img, page=1, kind="figure")
    assert report.kind == "figure"
    for d in report.defects:
        assert d.defect_id == "edge_overflow"
