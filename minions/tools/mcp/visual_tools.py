"""MCP tools for visual format-checking.

Exposes :mod:`minions.tools.visual_check` to Roles via FastMCP. The detection
engine is format-agnostic; these tool wrappers add path resolution, optional
report persistence, and structured-result Pydantic models.

Tool surface:

- ``mos_visual_render``   — rasterize a PDF to ``page_NNN.png``
- ``mos_visual_inspect``  — run detectors on a single image or a directory of
                            page images
- ``mos_visual_check``    — end-to-end: render PDF + inspect + (optionally) save

All tools honor ``_require_tool_allowed`` server-side authz.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from minions.tools import visual_check as _vc
from minions.tools.mcp import mcp
from minions.tools.mcp._common import _require_tool_allowed

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Argument models
# ---------------------------------------------------------------------------


class VisualRenderArgs(BaseModel):
    pdf_path: str = Field(description="Absolute path to a PDF.")
    output_dir: str | None = Field(
        default=None,
        description=(
            "Directory for ``page_NNN.png`` outputs. "
            "Defaults to ``<pdf_dir>/<pdf_stem>_pages/`` next to the PDF."
        ),
    )
    dpi: int = Field(default=220, ge=72, le=600, description="Render DPI.")


class VisualInspectArgs(BaseModel):
    target_path: str = Field(
        description=(
            "Absolute path to a PDF, a single rasterized image, or a directory "
            "containing page_*.png files."
        )
    )
    kind: Literal["auto", "layout", "figure"] = Field(
        default="auto",
        description=(
            "Detector profile. ``layout`` = full paper-page checks "
            "(column void, trailing whitespace, edge overflow, column "
            "imbalance, float clustering, short lines). ``figure`` = "
            "edge-overflow only. ``auto`` = layout for paper-sized images "
            "and double-column pages, figure otherwise."
        ),
    )
    report_path: str | None = Field(
        default=None,
        description=(
            "Optional absolute path to write the JSON DefectReport. Parent dirs are created."
        ),
    )


class VisualCheckArgs(BaseModel):
    pdf_path: str = Field(description="Absolute path to a PDF.")
    output_dir: str | None = Field(
        default=None,
        description="Directory for rendered page images. See ``mos_visual_render``.",
    )
    dpi: int = Field(default=220, ge=72, le=600)
    kind: Literal["layout", "figure"] = Field(default="layout")
    report_path: str | None = Field(default=None, description="Optional JSON report output path.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in _IMAGE_EXTS


def _gather_page_images(directory: Path) -> list[Path]:
    """Collect ``page_NNN.png`` (or any image) files in stable page order."""
    candidates = sorted(
        (p for p in directory.iterdir() if _is_image(p)),
        key=lambda p: p.name.lower(),
    )
    if not candidates:
        raise _vc.VisualCheckError(f"No page images found in directory: {directory}")
    return candidates


def _persist_report(report: _vc.DefectReport, target: Path | None) -> str | None:
    if target is None:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return str(target.resolve())


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def mos_visual_render(args: VisualRenderArgs) -> dict:
    """Rasterize a PDF to per-page PNG images via Poppler.

    Returns ``{output_dir, dpi, page_count, page_files}``. Raises a
    PermissionError if the calling role is not authorized for visual tools,
    or a RuntimeError if Poppler is unavailable.
    """
    _require_tool_allowed("mos_visual_render")
    pdf = Path(args.pdf_path).expanduser().resolve()
    out_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else pdf.parent / f"{pdf.stem}_pages"
    )
    pages = _vc.render_pdf_to_pages(pdf, out_dir, dpi=args.dpi)
    return {
        "pdf_path": str(pdf),
        "output_dir": str(out_dir),
        "dpi": args.dpi,
        "page_count": len(pages),
        "page_files": [str(p) for p in pages],
    }


@mcp.tool()
def mos_visual_inspect(args: VisualInspectArgs) -> dict:
    """Run visual detectors on a PDF, single image, or a directory of pages.

    Returns the structured ``DefectReport`` as a dict. When ``report_path`` is
    set the same report is also persisted as JSON.
    """
    _require_tool_allowed("mos_visual_inspect")
    target = Path(args.target_path).expanduser().resolve()
    if not target.exists():
        raise _vc.VisualCheckError(f"target_path does not exist: {target}")

    if target.is_file() and target.suffix.lower() == ".pdf":
        report = _vc.inspect_pdf(
            target,
            output_dir=None,
            kind="layout" if args.kind in ("auto", "layout") else "figure",
        )
    elif _is_image(target):
        report = _vc.inspect_image(target, kind=args.kind)
    elif target.is_dir():
        pages = _gather_page_images(target)
        page_reports: list[_vc.PageReport] = []
        summary: dict[str, int] = {}
        for idx, p in enumerate(pages, start=1):
            page_no = _vc._page_index(p.name, idx)
            pr = _vc.inspect_page(p, page=page_no, kind=args.kind)
            page_reports.append(pr)
            for d in pr.defects:
                summary[d.defect_id] = summary.get(d.defect_id, 0) + 1
        report = _vc.DefectReport(
            source_path=str(target),
            source_kind="image",
            page_count=len(page_reports),
            pages=page_reports,
            summary=summary,
        )
    else:
        raise _vc.VisualCheckError(
            f"Unsupported target_path: {target} (expected PDF, image, or page dir)."
        )

    saved = _persist_report(
        report, Path(args.report_path).expanduser().resolve() if args.report_path else None
    )
    payload = json.loads(report.model_dump_json())
    if saved:
        payload["report_path"] = saved
    return payload


@mcp.tool()
def mos_visual_check(args: VisualCheckArgs) -> dict:
    """End-to-end: render the PDF, inspect every page, optionally save the report.

    Equivalent to calling ``mos_visual_render`` then ``mos_visual_inspect``
    on the resulting directory, but the rendered images stay on disk for
    later targeted re-inspection.
    """
    _require_tool_allowed("mos_visual_check")
    pdf = Path(args.pdf_path).expanduser().resolve()
    out_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else pdf.parent / f"{pdf.stem}_pages"
    )
    report = _vc.inspect_pdf(pdf, output_dir=out_dir, dpi=args.dpi, kind=args.kind)
    saved = _persist_report(
        report,
        Path(args.report_path).expanduser().resolve() if args.report_path else None,
    )
    payload = json.loads(report.model_dump_json())
    payload["page_images_dir"] = str(out_dir)
    if saved:
        payload["report_path"] = saved
    return payload
