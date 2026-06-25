from __future__ import annotations
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
        image_regions = [r for r in layout_regions if r.get("kind") == "image_candidate"]
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
        asset_dir = ctx.job_dir / "assets"
        for image_region in image_regions:
            x1, y1, x2, y2 = [int(round(value)) for value in image_region["bbox"]]
            asset_dir.mkdir(parents=True, exist_ok=True)
            asset_path = asset_dir / f"{image_region['id']}.png"
            im.crop((x1, y1, x2, y2)).save(asset_path)
            slide.elements.append(
                SlideElement(
                    id=image_region["id"],
                    type=ElementType.IMAGE,
                    bbox=Rect(x=x1, y=y1, width=x2 - x1, height=y2 - y1),
                    z_index=15,
                    confidence=image_region["confidence"],
                    provenance=Provenance(source="layout_parser", raw=image_region),
                    editable_strategy=EditableStrategy.RASTER_IMAGE,
                    asset_path=asset_path,
                )
            )
        for s in ctx.candidates.get("shapes", []):
            if _is_covered_by_region(s["bbox"], table_regions + image_regions, min_ratio=0.85):
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
            if _is_covered_by_region(t["bbox"], table_regions, min_ratio=0.8):
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
