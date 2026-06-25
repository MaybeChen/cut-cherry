from __future__ import annotations

import re

from PIL import Image
from image2pptx.ir.elements import (
    EditableStrategy,
    ElementStyle,
    ElementType,
    Provenance,
    Rect,
    SlideElement,
)
from image2pptx.ir.slide_ir import SlideIR
from image2pptx.pipeline.context import PipelineContext


class CandidateFusionProcessor:
    def run(self, ctx: PipelineContext) -> SlideIR:
        im = Image.open(ctx.artifacts["normalized"])
        slide = SlideIR(width=im.width, height=im.height)
        layout_regions = ctx.candidates.get("layout_regions", [])
        table_regions = [r for r in layout_regions if r.get("kind") == "table_candidate"]
        image_regions = [
            r for r in layout_regions if r.get("kind") in {"image_candidate", "logo_candidate"}
        ]
        formula_regions = ctx.candidates.get("formulas", [])
        chart_regions = ctx.candidates.get("charts", [])
        # 简单背景使用原生纯色，避免整页原图伪背景。
        slide.elements.append(
            SlideElement(
                id="background",
                type=ElementType.BACKGROUND,
                bbox=Rect(x=0, y=0, width=im.width, height=im.height),
                z_index=0,
                style=ElementStyle(fill_color="#ffffff"),
                provenance=Provenance(source="background_processor"),
                editable_strategy=EditableStrategy.NATIVE_SHAPE,
            )
        )
        for table in table_regions:
            x1, y1, x2, y2 = table["bbox"]
            slide.elements.append(
                SlideElement(
                    id=table["id"],
                    type=ElementType.TABLE,
                    bbox=Rect(x=x1, y=y1, width=x2 - x1, height=y2 - y1),
                    z_index=45,
                    style=ElementStyle(fill_color="#ffffff", line_color="#666666"),
                    confidence=table["confidence"],
                    provenance=Provenance(source="layout_parser", raw=table),
                    editable_strategy=EditableStrategy.NATIVE_TABLE,
                )
            )
        asset_root = ctx.job_dir / "assets"
        for image_region in image_regions:
            asset = _prepare_image_asset(im, image_region, asset_root)
            if not asset:
                continue
            x1, y1, x2, y2 = asset["bbox"]
            element_type = ElementType.LOGO if asset["kind"] == "logo" else ElementType.IMAGE
            raw_region = dict(image_region)
            raw_region["asset"] = {
                "path": str(asset["path"]),
                "kind": asset["kind"],
                "bbox": asset["bbox"],
            }
            slide.elements.append(
                SlideElement(
                    id=image_region["id"],
                    type=element_type,
                    bbox=Rect(x=x1, y=y1, width=x2 - x1, height=y2 - y1),
                    z_index=40 if element_type == ElementType.LOGO else 15,
                    confidence=image_region["confidence"],
                    provenance=Provenance(source="layout_parser", raw=raw_region),
                    editable_strategy=(
                        EditableStrategy.TRANSPARENT_PNG
                        if element_type == ElementType.LOGO
                        else EditableStrategy.RASTER_IMAGE
                    ),
                    asset_path=asset["path"],
                )
            )
        for formula in formula_regions:
            x1, y1, x2, y2 = formula["bbox"]
            slide.elements.append(
                SlideElement(
                    id=formula["id"],
                    type=ElementType.FORMULA,
                    bbox=Rect(x=x1, y=y1, width=x2 - x1, height=y2 - y1),
                    z_index=55,
                    text=formula["text"],
                    style=ElementStyle(
                        font_family="Cambria Math", font_size=max(10, (y2 - y1) * 0.5)
                    ),
                    confidence=formula["confidence"],
                    provenance=Provenance(source="formula_processor", raw=formula),
                    editable_strategy=EditableStrategy.OFFICE_MATH,
                )
            )
        for chart in chart_regions:
            x1, y1, x2, y2 = chart["bbox"]
            slide.elements.append(
                SlideElement(
                    id=chart["id"],
                    type=ElementType.CHART,
                    bbox=Rect(x=x1, y=y1, width=x2 - x1, height=y2 - y1),
                    z_index=35,
                    style=ElementStyle(fill_color="#ffffff", line_color="#666666"),
                    confidence=chart["confidence"],
                    provenance=Provenance(source="chart_processor", raw=chart),
                    editable_strategy=EditableStrategy.NATIVE_CHART,
                )
            )
        for s in ctx.candidates.get("shapes", []):
            if _is_covered_by_region(
                s["bbox"],
                table_regions + image_regions + chart_regions,
                min_ratio=0.85,
            ):
                continue
            x1, y1, x2, y2 = s["bbox"]
            slide.elements.append(
                SlideElement(
                    id=s["id"],
                    type=ElementType.SHAPE,
                    bbox=Rect(x=x1, y=y1, width=x2 - x1, height=y2 - y1),
                    z_index=10,
                    style=ElementStyle(
                        fill_color=s.get("fill_color"),
                        line_color="#666666",
                        shape_type=s.get("kind"),
                    ),
                    confidence=s["confidence"],
                    provenance=Provenance(source="opencv", raw=s),
                    editable_strategy=EditableStrategy.NATIVE_SHAPE,
                )
            )
        text_candidates = ctx.candidates.get("text_blocks") or ctx.candidates.get("text", [])
        for t in text_candidates:
            if _is_covered_by_region(t["bbox"], table_regions + formula_regions, min_ratio=0.8):
                continue
            x1, y1, x2, y2 = t["bbox"]
            font_size = None
            bold = False
            if t.get("kind") == "title":
                font_size = max(18, (y2 - y1) * 0.55)
                bold = True
            style = ElementStyle(font_size=font_size, bold=bold)
            slide.elements.append(
                SlideElement(
                    id=t["id"],
                    type=ElementType.TEXT,
                    bbox=Rect(x=x1, y=y1, width=x2 - x1, height=y2 - y1),
                    z_index=50,
                    text=t["text"],
                    style=style,
                    confidence=t["confidence"],
                    provenance=Provenance(
                        source="layout_parser" if ctx.candidates.get("text_blocks") else "ocr",
                        raw=t,
                    ),
                    editable_strategy=EditableStrategy.NATIVE_TEXT,
                )
            )
        for c in ctx.candidates.get("connectors", [])[:50]:
            (x1, y1), (x2, y2) = c["points"]
            slide.elements.append(
                SlideElement(
                    id=c["id"],
                    type=ElementType.CONNECTOR,
                    bbox=Rect(
                        x=min(x1, x2),
                        y=min(y1, y2),
                        width=abs(x2 - x1) or 1,
                        height=abs(y2 - y1) or 1,
                    ),
                    z_index=20,
                    style=ElementStyle(line_color="#000000"),
                    confidence=c["confidence"],
                    provenance=Provenance(source="opencv_hough", raw=c),
                    editable_strategy=EditableStrategy.NATIVE_CONNECTOR,
                )
            )
        slide.validate_scene()
        slide.relations.extend(slide.find_overlaps(0.2))
        return slide


def _is_covered_by_region(bbox: list[float], regions: list[dict], min_ratio: float) -> bool:
    return any(_overlap_ratio(bbox, region["bbox"]) >= min_ratio for region in regions)


def _overlap_ratio(a: list[float], b: list[float]) -> float:
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    return inter / area if area else 0.0


def _prepare_image_asset(im: Image.Image, region: dict, asset_root) -> dict | None:
    crop_box = _bounded_crop_box(region.get("bbox", []), im.width, im.height)
    if crop_box is None:
        return None
    kind = _asset_kind(region, crop_box, im.width, im.height)
    asset_dir = asset_root / ("logos" if kind == "logo" else "images")
    asset_dir.mkdir(parents=True, exist_ok=True)
    asset_path = asset_dir / f"{_safe_asset_name(region.get('id', kind))}.png"
    im.crop(crop_box).save(asset_path)
    return {"kind": kind, "path": asset_path, "bbox": list(crop_box)}


def _bounded_crop_box(
    bbox: list[float], width: int, height: int
) -> tuple[int, int, int, int] | None:
    if len(bbox) != 4:
        return None
    x1, y1, x2, y2 = [int(round(float(value))) for value in bbox]
    x1 = max(0, min(width, x1))
    y1 = max(0, min(height, y1))
    x2 = max(0, min(width, x2))
    y2 = max(0, min(height, y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _asset_kind(region: dict, crop_box: tuple[int, int, int, int], width: int, height: int) -> str:
    label = " ".join(
        str(value).lower()
        for value in (
            region.get("kind"),
            region.get("label"),
            region.get("category"),
            region.get("type"),
        )
        if value
    )
    if "logo" in label:
        return "logo"
    x1, y1, x2, y2 = crop_box
    box_w = x2 - x1
    box_h = y2 - y1
    area_ratio = (box_w * box_h) / max(width * height, 1)
    in_brand_band = y1 <= height * 0.18 or y2 >= height * 0.88
    compact = area_ratio <= 0.08 and box_w <= width * 0.42 and box_h <= height * 0.28
    near_edge = x1 <= width * 0.18 or x2 >= width * 0.82
    return "logo" if in_brand_band and compact and near_edge else "image"


def _safe_asset_name(value: object) -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._")
    return name or "asset"
