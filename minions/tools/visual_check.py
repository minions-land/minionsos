"""Visual format-check engine for MinionsOS.

A format-agnostic visual defect detector for PDFs and rasterized images.
Adapted from the open-source PaperFit project (visual typesetting optimization
for LaTeX papers); the LaTeX-specific machinery has been stripped, keeping the
portable computer-vision core: Otsu thresholding, row-wise ink projection,
morphological closing for object extraction, and density-band statistics.

Detector inventory (all pixel-level, no document-format knowledge):

- ``detect_column_void``       — empty vertical band inside one column of a
                                 double-column layout (PaperFit A5)
- ``detect_trailing_whitespace`` — large empty strip at the bottom of a page (A2)
- ``detect_overflow_at_margins`` — dark pixels past the inner safe margin (D1)
- ``detect_column_imbalance``  — content-height delta between left and right
                                 columns (A4)
- ``detect_float_clustering``  — figure/table-like blocks stacked too close (B3)
- ``detect_short_lines``       — short final lines suggesting widows / orphans (A1)

The orchestrator entry points are :func:`inspect_page` (single image) and
:func:`inspect_pdf` (full document). Both return a :class:`DefectReport` of
generic, format-agnostic defects rather than VTO category codes.

PaperFit references retained for traceability:
``other/PaperFit-main/scripts/{detect_column_void.py,cv_detector.py,
render_pages.py}``.

Dependencies:

- ``opencv-python-headless`` for image analysis
- ``pdf2image`` + Poppler for PDF rasterization
- ``Pillow`` and ``numpy`` (transitive)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Heavy deps are optional (pip install minionsos[visual]).
# Import them lazily so the MCP server starts even without opencv/pdf2image.
_VISUAL_MISSING: str | None = None
try:
    import cv2
    import numpy as np
    from pdf2image import convert_from_path
    from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError
except ImportError as _e:  # pragma: no cover
    _VISUAL_MISSING = (
        f"Visual tools are not installed: {_e}. Run: uv pip install 'minionsos[visual]'"
    )
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]
    convert_from_path = None  # type: ignore[assignment]
    PDFInfoNotInstalledError = Exception  # type: ignore[assignment,misc]
    PDFPageCountError = Exception  # type: ignore[assignment,misc]


def _require_visual() -> None:
    """Raise a clear error if the visual extras are not installed."""
    if _VISUAL_MISSING:
        raise RuntimeError(_VISUAL_MISSING)


logger = logging.getLogger(__name__)

# Format-agnostic vocabulary — see minions/domains/visual-format-taxonomy.md.
DefectId = Literal[
    "column_void",
    "trailing_whitespace",
    "edge_overflow",
    "column_imbalance",
    "float_clustering",
    "short_line",
]
Severity = Literal["minor", "major", "critical"]
PageKind = Literal["layout", "figure", "auto"]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class LayoutRules(BaseModel):
    """Tunable thresholds for the visual detectors.

    Defaults track PaperFit's ``config/layout_rules.yaml`` and have been
    validated on academic two-column papers at 220 DPI. Override per-call when
    inspecting figures or non-standard layouts.
    """

    # Column-void detector
    min_void_ratio: float = Field(default=0.30, ge=0.0, le=1.0)
    min_void_lines: int = Field(default=8, ge=1)
    void_row_thresh: float = Field(default=0.035, ge=0.0, le=1.0)
    smooth_rows: int = Field(default=7, ge=1)
    merge_gap_pixels: int = Field(default=12, ge=0)

    # Trailing-whitespace detector
    trailing_whitespace_threshold: float = Field(default=0.20, ge=0.0, le=1.0)
    trailing_whitespace_major_ratio: float = Field(default=0.30, ge=0.0, le=1.0)
    whitespace_pixel_threshold: int = Field(default=240, ge=0, le=255)

    # Edge-overflow detector
    overflow_margin_px: int = Field(default=20, ge=1)
    overflow_dark_pixel_threshold: int = Field(default=50, ge=0, le=255)
    overflow_min_pixels: int = Field(default=100, ge=1)

    # Column-imbalance detector
    column_imbalance_threshold: float = Field(default=0.10, ge=0.0, le=1.0)
    column_imbalance_major_threshold: float = Field(default=0.15, ge=0.0, le=1.0)
    column_binarize_threshold: int = Field(default=200, ge=0, le=255)

    # Float-clustering detector
    float_clustering_min_distance_px: int = Field(default=100, ge=0)
    float_kernel_size: int = Field(default=15, ge=3)
    float_min_width_ratio: float = Field(default=0.30, ge=0.0, le=1.0)
    float_min_height_px: int = Field(default=150, ge=1)
    float_max_height_ratio: float = Field(default=0.80, ge=0.0, le=1.0)
    float_min_density: float = Field(default=0.10, ge=0.0, le=1.0)

    # Short-line detector (A1)
    short_line_width_ratio: float = Field(default=0.30, ge=0.0, le=1.0)

    # Generic content-binarization
    content_binary_threshold: int = Field(default=240, ge=0, le=255)

    @field_validator("smooth_rows")
    @classmethod
    def _odd_smooth(cls, v: int) -> int:
        return v if v % 2 == 1 else v + 1


class Defect(BaseModel):
    """One structured visual defect."""

    defect_id: DefectId
    severity: Severity
    page: int = Field(ge=1, description="1-based page number; 1 for single images.")
    location: str = Field(default="", description="Human-readable region identifier.")
    description: str
    metrics: dict[str, float | int] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class PageReport(BaseModel):
    """Per-page inspection result."""

    page: int
    image_path: str
    width: int
    height: int
    kind: Literal["layout", "figure"]
    is_double_column: bool
    defects: list[Defect] = Field(default_factory=list)


class DefectReport(BaseModel):
    """Top-level report aggregating every page's findings."""

    schema_version: str = "1.0"
    source_path: str
    source_kind: Literal["pdf", "image"]
    page_count: int
    pages: list[PageReport] = Field(default_factory=list)
    summary: dict[str, int] = Field(
        default_factory=dict,
        description="Histogram of defect_id → count across all pages.",
    )

    def critical_or_major_defects(self) -> list[Defect]:
        out: list[Defect] = []
        for p in self.pages:
            out.extend(d for d in p.defects if d.severity in ("major", "critical"))
        return out


# ---------------------------------------------------------------------------
# CV primitives
# ---------------------------------------------------------------------------


def _load_gray(image_path: Path) -> np.ndarray | None:
    bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if bgr is None:
        return None
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)


def _ink_threshold(gray: np.ndarray) -> int:
    """Otsu threshold on a Gaussian-blurred copy; clamp into a usable band."""
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    t, _ = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if t <= 0 or t >= 255:
        return 200
    return int(min(220, max(120, t + 15)))


def _smooth_1d(arr: np.ndarray, k: int) -> np.ndarray:
    k = max(1, k | 1)
    if k == 1:
        return arr
    kernel = np.ones(k, dtype=np.float32) / float(k)
    pad = k // 2
    padded = np.pad(arr, (pad, pad), mode="edge")
    return np.convolve(padded, kernel, mode="valid").astype(np.float32)


def _find_gutter_x(gray: np.ndarray, lo: float = 0.33, hi: float = 0.67) -> int:
    """Locate the brightest vertical band in the page midline (the gutter)."""
    _, w = gray.shape[:2]
    x0 = max(1, int(w * lo))
    x1 = min(w - 2, int(w * hi))
    win = max(3, w // 200 | 1)
    if win % 2 == 0:
        win += 1
    best_x = (x0 + x1) // 2
    best_score = -1.0
    for xc in range(x0, x1):
        x_lo = max(0, xc - win // 2)
        x_hi = min(w, xc + win // 2 + 1)
        score = float(gray[:, x_lo:x_hi].mean())
        if score > best_score:
            best_score = score
            best_x = xc
    return int(best_x)


def _looks_double_column(gray: np.ndarray) -> bool:
    """Heuristic: the gutter region must be much brighter than column means."""
    h, w = gray.shape[:2]
    if w < 600 or h < 600:
        return False
    gx = _find_gutter_x(gray)
    if not (w * 0.35 <= gx <= w * 0.65):
        return False
    win = max(6, w // 100)
    gutter = gray[:, max(0, gx - win // 2) : min(w, gx + win // 2)].mean()
    left = gray[:, : max(1, gx - win)].mean()
    right = gray[:, min(w - 1, gx + win) :].mean()
    column_mean = (left + right) / 2.0
    return bool(gutter - column_mean > 18.0)


def _content_binary(gray: np.ndarray, threshold: int) -> np.ndarray:
    _, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)
    return binary


def _find_float_bboxes(binary: np.ndarray, rules: LayoutRules) -> list[tuple[int, int, int, int]]:
    """Return float-like bounding boxes (x, y, w, h) sorted top-to-bottom."""
    h, w = binary.shape
    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (rules.float_kernel_size, rules.float_kernel_size)
    )
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out: list[tuple[int, int, int, int]] = []
    min_w = w * rules.float_min_width_ratio
    max_h = h * rules.float_max_height_ratio
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        if cw <= min_w or ch <= rules.float_min_height_px or ch >= max_h:
            continue
        roi = closed[y : y + ch, x : x + cw]
        density = float(np.sum(roi > 0)) / float(max(cw * ch, 1))
        if density >= rules.float_min_density:
            out.append((x, y, cw, ch))
    out.sort(key=lambda b: b[1])
    return out


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------


@dataclass
class _VoidSeg:
    y0: int
    y1: int
    height_px: int
    ratio: float


def _column_void_segments(
    col_gray: np.ndarray,
    ink_thr: int,
    rules: LayoutRules,
    min_gap_px: int,
) -> list[_VoidSeg]:
    ink = (col_gray < ink_thr).astype(np.float32)
    row_ink = ink.mean(axis=1)
    row_smooth = _smooth_1d(row_ink, rules.smooth_rows)
    is_void = row_smooth < rules.void_row_thresh

    raw: list[tuple[int, int]] = []
    i = 0
    n = len(is_void)
    while i < n:
        if not is_void[i]:
            i += 1
            continue
        j = i
        while j < n and is_void[j]:
            j += 1
        if j - i >= min_gap_px:
            raw.append((i, j))
        i = j

    merged: list[tuple[int, int]] = []
    for y0, y1 in raw:
        if merged and y0 - merged[-1][1] <= rules.merge_gap_pixels:
            merged[-1] = (merged[-1][0], y1)
        else:
            merged.append((y0, y1))

    col_h = col_gray.shape[0]
    out: list[_VoidSeg] = []
    for y0, y1 in merged:
        hpx = y1 - y0
        ratio = hpx / float(max(1, col_h))
        if ratio >= rules.min_void_ratio and hpx >= min_gap_px:
            out.append(_VoidSeg(y0=y0, y1=y1, height_px=hpx, ratio=round(ratio, 4)))
    return out


def _estimate_line_height(gray: np.ndarray) -> int:
    """Median spacing between horizontal-gradient peaks; fallback 18 px."""
    grad = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    row_act = np.abs(grad).mean(axis=1)
    peaks = np.where(row_act > np.percentile(row_act, 85))[0]
    if len(peaks) <= 10:
        return 18
    diffs = np.diff(np.sort(peaks))
    diffs = diffs[diffs > 3]
    return int(np.median(diffs)) if len(diffs) else 18


def detect_column_void(gray: np.ndarray, page: int, rules: LayoutRules) -> list[Defect]:
    """Find vertical empty bands inside a single column of a 2-column layout."""
    if not _looks_double_column(gray):
        return []
    gx = _find_gutter_x(gray)
    line_h = _estimate_line_height(gray)
    min_gap_px = max(12, int(rules.min_void_lines * line_h * 0.85))
    ink_thr = _ink_threshold(gray)

    defects: list[Defect] = []
    for col_name, crop in (("left", gray[:, :gx]), ("right", gray[:, gx:])):
        for seg in _column_void_segments(crop, ink_thr, rules, min_gap_px):
            severity: Severity = "critical" if seg.ratio >= 0.50 else "major"
            defects.append(
                Defect(
                    defect_id="column_void",
                    severity=severity,
                    page=page,
                    location=f"{col_name} column, y={seg.y0}-{seg.y1} px",
                    description=(
                        f"Empty vertical band covers {seg.ratio:.0%} of the "
                        f"{col_name} column (no ink, no figure, no table)."
                    ),
                    metrics={
                        "void_ratio": float(seg.ratio),
                        "void_height_px": int(seg.height_px),
                        "y0": int(seg.y0),
                        "y1": int(seg.y1),
                    },
                    confidence=0.9 if seg.ratio >= 0.4 else 0.7,
                )
            )
    return defects


def detect_trailing_whitespace(gray: np.ndarray, page: int, rules: LayoutRules) -> list[Defect]:
    """Empty strip below the lowest content pixel."""
    pixel_thr = rules.whitespace_pixel_threshold
    binary = _content_binary(gray, pixel_thr)
    content_rows = np.where(np.any(binary > 0, axis=1))[0]
    h, w = gray.shape
    if len(content_rows) == 0:
        ratio = 1.0
        content_bottom = 0
    else:
        content_bottom = int(content_rows.max())
        trailing_pixels = max(0, h - content_bottom - 1) * w
        ratio = trailing_pixels / float(max(h * w, 1))
    if ratio <= rules.trailing_whitespace_threshold:
        return []
    severity: Severity = "major" if ratio >= rules.trailing_whitespace_major_ratio else "minor"
    return [
        Defect(
            defect_id="trailing_whitespace",
            severity=severity,
            page=page,
            location=f"below y={content_bottom} px",
            description=f"Trailing whitespace covers {ratio:.0%} of the page.",
            metrics={
                "trailing_ratio": float(round(ratio, 4)),
                "content_bottom_px": int(content_bottom),
            },
        )
    ]


def detect_overflow_at_margins(gray: np.ndarray, page: int, rules: LayoutRules) -> list[Defect]:
    """Dark pixels past the inner margin band (right edge is the typical hit)."""
    h, w = gray.shape
    m = rules.overflow_margin_px
    dark = rules.overflow_dark_pixel_threshold
    min_pixels = rules.overflow_min_pixels
    right = int(np.sum(gray[:, w - m :] < dark))
    bottom = int(np.sum(gray[h - m :, :] < dark))
    out: list[Defect] = []
    if right > min_pixels:
        out.append(
            Defect(
                defect_id="edge_overflow",
                severity="major",
                page=page,
                location="right margin",
                description=f"{right} dark pixels intrude on the right margin.",
                metrics={"right_overflow_px": right},
                confidence=0.75,
            )
        )
    if bottom > min_pixels:
        out.append(
            Defect(
                defect_id="edge_overflow",
                severity="major",
                page=page,
                location="bottom margin",
                description=f"{bottom} dark pixels intrude on the bottom margin.",
                metrics={"bottom_overflow_px": bottom},
                confidence=0.75,
            )
        )
    return out


def detect_column_imbalance(gray: np.ndarray, page: int, rules: LayoutRules) -> list[Defect]:
    """Content-height delta between the two columns of a 2-column layout."""
    if not _looks_double_column(gray):
        return []
    gx = _find_gutter_x(gray)
    binary = _content_binary(gray, rules.column_binarize_threshold)
    left_h = int(np.sum(np.any(binary[:, :gx] > 0, axis=1)))
    right_h = int(np.sum(np.any(binary[:, gx:] > 0, axis=1)))
    max_h = max(left_h, right_h)
    if max_h == 0:
        return []
    diff_ratio = abs(left_h - right_h) / max_h
    if diff_ratio <= rules.column_imbalance_threshold:
        return []
    severity: Severity = (
        "major" if diff_ratio >= rules.column_imbalance_major_threshold else "minor"
    )
    return [
        Defect(
            defect_id="column_imbalance",
            severity=severity,
            page=page,
            location="left vs right column",
            description=(
                f"Column heights differ by {diff_ratio:.0%} (left={left_h}px, right={right_h}px)."
            ),
            metrics={
                "height_diff_ratio": float(round(diff_ratio, 4)),
                "left_height_px": left_h,
                "right_height_px": right_h,
            },
            confidence=0.85,
        )
    ]


def detect_float_clustering(gray: np.ndarray, page: int, rules: LayoutRules) -> list[Defect]:
    """Adjacent figure/table-like blocks separated by less than min_distance."""
    binary = _content_binary(gray, rules.content_binary_threshold)
    boxes = _find_float_bboxes(binary, rules)
    out: list[Defect] = []
    min_dist = rules.float_clustering_min_distance_px
    for cur, nxt in pairwise(boxes):
        cur_bottom = cur[1] + cur[3]
        gap = nxt[1] - cur_bottom
        x_overlap = max(cur[0], nxt[0]) < min(cur[0] + cur[2], nxt[0] + nxt[2])
        if 0 <= gap < min_dist and x_overlap:
            out.append(
                Defect(
                    defect_id="float_clustering",
                    severity="minor",
                    page=page,
                    location=f"y≈{cur[1]}-{nxt[1] + nxt[3]} px",
                    description=(
                        f"Two float-like blocks separated by only {gap}px (threshold {min_dist}px)."
                    ),
                    metrics={"vertical_gap_px": int(gap), "float_count": 2},
                    confidence=0.75,
                )
            )
    return out


def detect_short_lines(gray: np.ndarray, page: int, rules: LayoutRules) -> list[Defect]:
    """Last text line shorter than ``short_line_width_ratio`` of column width."""
    if not _looks_double_column(gray):
        return _detect_short_lines_in_column(gray, page, rules, "page")
    gx = _find_gutter_x(gray)
    out: list[Defect] = []
    out.extend(_detect_short_lines_in_column(gray[:, :gx], page, rules, "left column"))
    out.extend(_detect_short_lines_in_column(gray[:, gx:], page, rules, "right column"))
    return out


def _detect_short_lines_in_column(
    col_gray: np.ndarray, page: int, rules: LayoutRules, where: str
) -> list[Defect]:
    """Heuristic A1: scan text bands; report a short final band as a candidate."""
    h, w = col_gray.shape
    if h < 200 or w < 200:
        return []
    binary = _content_binary(col_gray, rules.content_binary_threshold)
    row_density = np.mean(binary > 0, axis=1)
    threshold = max(0.01, float(np.mean(row_density) * 0.55))
    bands: list[tuple[int, int]] = []
    in_band = False
    start = 0
    for idx, val in enumerate(row_density):
        if val > threshold and not in_band:
            in_band = True
            start = idx
        elif val <= threshold and in_band:
            in_band = False
            if idx - start >= 6:
                bands.append((start, idx))
    if in_band and len(row_density) - start >= 6:
        bands.append((start, len(row_density)))
    if not bands:
        return []
    last_y0, last_y1 = bands[-1]
    band_width = int(np.sum(np.any(binary[last_y0:last_y1, :] > 0, axis=0)))
    width_ratio = band_width / float(max(w, 1))
    if width_ratio >= rules.short_line_width_ratio:
        return []
    return [
        Defect(
            defect_id="short_line",
            severity="minor",
            page=page,
            location=f"{where}, last band y={last_y0}-{last_y1} px",
            description=(
                f"Final text band fills only {width_ratio:.0%} of the column width "
                f"(possible widow / orphan / short tail)."
            ),
            metrics={"width_ratio": float(round(width_ratio, 4))},
            confidence=0.6,
        )
    ]


# ---------------------------------------------------------------------------
# Orchestrators
# ---------------------------------------------------------------------------


_LAYOUT_DETECTORS = (
    detect_column_void,
    detect_trailing_whitespace,
    detect_overflow_at_margins,
    detect_column_imbalance,
    detect_float_clustering,
    detect_short_lines,
)
_FIGURE_DETECTORS = (detect_overflow_at_margins,)


class VisualCheckError(RuntimeError):
    """Raised when input cannot be loaded or rasterized."""


def inspect_page(
    image_path: Path,
    page: int = 1,
    kind: PageKind = "auto",
    rules: LayoutRules | None = None,
) -> PageReport:
    """Run all applicable detectors on a single rasterized page image."""
    _require_visual()
    image_path = Path(image_path)
    rules = rules or LayoutRules()
    gray = _load_gray(image_path)
    if gray is None:
        raise VisualCheckError(f"Cannot read image: {image_path}")
    h, w = gray.shape
    is_double = _looks_double_column(gray)
    resolved_kind: Literal["layout", "figure"]
    if kind == "auto":
        resolved_kind = "layout" if is_double or max(h, w) >= 1500 else "figure"
    else:
        resolved_kind = kind
    detectors = _LAYOUT_DETECTORS if resolved_kind == "layout" else _FIGURE_DETECTORS
    defects: list[Defect] = []
    for det in detectors:
        try:
            defects.extend(det(gray, page, rules))
        except Exception:
            logger.exception("Detector %s failed on %s", det.__name__, image_path)
    return PageReport(
        page=page,
        image_path=str(image_path),
        width=w,
        height=h,
        kind=resolved_kind,
        is_double_column=is_double,
        defects=defects,
    )


def render_pdf_to_pages(pdf_path: Path, output_dir: Path, dpi: int = 220) -> list[Path]:
    """Rasterize a PDF to ``page_NNN.png`` images via Poppler."""
    _require_visual()
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    if not pdf_path.is_file():
        raise VisualCheckError(f"PDF not found: {pdf_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        images = convert_from_path(str(pdf_path), dpi=dpi, fmt="png", thread_count=2)
    except (PDFInfoNotInstalledError, PDFPageCountError) as exc:
        raise VisualCheckError(
            f"Poppler unavailable or PDF unreadable ({pdf_path}): {exc}. "
            "Install Poppler (brew install poppler) or supply page images directly."
        ) from exc
    out_paths: list[Path] = []
    for i, page in enumerate(images, start=1):
        target = output_dir / f"page_{i:03d}.png"
        page.save(target, "PNG")
        out_paths.append(target)
    return out_paths


_PAGE_INDEX_RE = re.compile(r"page_(\d+)", re.IGNORECASE)


def _page_index(name: str, fallback: int) -> int:
    m = _PAGE_INDEX_RE.search(name)
    return int(m.group(1)) if m else fallback


def inspect_pdf(
    pdf_path: Path,
    output_dir: Path | None = None,
    dpi: int = 220,
    kind: PageKind = "layout",
    rules: LayoutRules | None = None,
) -> DefectReport:
    """End-to-end pipeline: render PDF → inspect each page → aggregate report."""
    pdf_path = Path(pdf_path)
    if output_dir is None:
        output_dir = pdf_path.with_suffix("").parent / f"{pdf_path.stem}_pages"
    page_paths = render_pdf_to_pages(pdf_path, Path(output_dir), dpi=dpi)
    pages: list[PageReport] = []
    summary: dict[str, int] = {}
    for fallback_idx, p in enumerate(page_paths, start=1):
        page_no = _page_index(p.name, fallback_idx)
        report = inspect_page(p, page=page_no, kind=kind, rules=rules)
        pages.append(report)
        for d in report.defects:
            summary[d.defect_id] = summary.get(d.defect_id, 0) + 1
    return DefectReport(
        source_path=str(pdf_path),
        source_kind="pdf",
        page_count=len(pages),
        pages=pages,
        summary=summary,
    )


def inspect_image(
    image_path: Path,
    kind: PageKind = "auto",
    rules: LayoutRules | None = None,
) -> DefectReport:
    """Inspect a single rasterized image (figure, table screenshot, etc.)."""
    image_path = Path(image_path)
    page_report = inspect_page(image_path, page=1, kind=kind, rules=rules)
    summary: dict[str, int] = {}
    for d in page_report.defects:
        summary[d.defect_id] = summary.get(d.defect_id, 0) + 1
    return DefectReport(
        source_path=str(image_path),
        source_kind="image",
        page_count=1,
        pages=[page_report],
        summary=summary,
    )
