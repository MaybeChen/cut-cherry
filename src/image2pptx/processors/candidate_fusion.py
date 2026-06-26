from __future__ import annotations

import json
import re
import base64
import io

from PIL import Image, ImageDraw
from image2pptx.ir.elements import (
    EditableStrategy,
    ElementStyle,
    ElementType,
    Provenance,
    Rect,
    SlideElement,
)
from image2pptx.ir.slide_ir import SlideIR
from image2pptx.models.rmbg import RmbgAdapter
from image2pptx.core.errors import PipelineStageError, format_stage_failure
from image2pptx.pipeline.context import PipelineContext


class CandidateFusionProcessor:
    def run(self, ctx: PipelineContext) -> SlideIR:
        im = Image.open(ctx.artifacts["normalized"])
        slide = SlideIR(width=im.width, height=im.height)
        layout_regions = ctx.candidates.get("layout_regions", [])
        table_regions = [r for r in layout_regions if r.get("kind") == "table_candidate"]
        image_regions = [
            r
            for r in layout_regions
            if r.get("kind") in {"image_candidate", "logo_candidate", "icon_candidate"}
        ]
        asset_image_regions, structural_image_regions = _split_asset_image_regions(ctx, image_regions, im)
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
        asset_root.mkdir(parents=True, exist_ok=True)
        asset_manifest = _start_asset_manifest(ctx, asset_root, image_regions)
        for structural_region in structural_image_regions:
            _record_asset_manifest_item(
                asset_manifest,
                structural_region,
                status="skipped_structural_container",
            )
            _print_asset_event(
                "skip",
                f"id={structural_region.get('id')} reason=structural_container bbox={structural_region.get('bbox')}",
            )
        _print_asset_event(
            "start",
            f"image/logo/icon candidates={len(asset_image_regions)} skipped_structural={len(structural_image_regions)} output={asset_root}",
        )
        if not asset_image_regions:
            _print_asset_event(
                "skip", "no image_candidate/logo_candidate/icon_candidate regions found"
            )
        for image_region in asset_image_regions:
            _print_asset_event(
                "candidate",
                f"id={image_region.get('id')} kind={image_region.get('kind')} bbox={image_region.get('bbox')}",
            )
            asset = _prepare_image_asset(im, image_region, asset_root, ctx)
            if not asset:
                _record_asset_manifest_item(
                    asset_manifest, image_region, status="skipped_invalid_bbox"
                )
                _print_asset_event(
                    "skip",
                    f"id={image_region.get('id')} reason=invalid_or_empty_bbox",
                )
                continue
            x1, y1, x2, y2 = asset["bbox"]
            element_type = _asset_element_type(asset["kind"])
            raw_region = dict(image_region)
            raw_region["asset"] = {
                "path": str(asset["path"]),
                "kind": asset["kind"],
                "bbox": asset["bbox"],
            }
            _record_asset_manifest_item(
                asset_manifest,
                image_region,
                status="saved",
                asset=asset,
                element_type=str(element_type),
            )
            _print_asset_event(
                "saved",
                f"id={image_region.get('id')} type={element_type} path={asset['path']} bbox={asset['bbox']}",
            )
            slide.elements.append(
                SlideElement(
                    id=image_region["id"],
                    type=element_type,
                    bbox=Rect(x=x1, y=y1, width=x2 - x1, height=y2 - y1),
                    z_index=40 if element_type in {ElementType.LOGO, ElementType.ICON} else 15,
                    confidence=image_region["confidence"],
                    provenance=Provenance(source="layout_parser", raw=raw_region),
                    editable_strategy=(
                        EditableStrategy.TRANSPARENT_PNG
                        if element_type in {ElementType.LOGO, ElementType.ICON}
                        else EditableStrategy.RASTER_IMAGE
                    ),
                    asset_path=asset["path"],
                )
            )
        _write_asset_manifest(ctx, asset_root, asset_manifest)
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
                table_regions + asset_image_regions + chart_regions,
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
                        line_color=s.get("line_color", "#666666"),
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
            if _is_covered_by_region(t["bbox"], asset_image_regions, min_ratio=0.6):
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


def _split_asset_image_regions(
    ctx: PipelineContext, image_regions: list[dict], im: Image.Image
) -> tuple[list[dict], list[dict]]:
    asset_regions = []
    structural_regions = []
    for region in image_regions:
        if _is_structural_container_image(region, ctx, im):
            structural_regions.append(region)
        else:
            asset_regions.append(region)
    return asset_regions, structural_regions


def _is_structural_container_image(region: dict, ctx: PipelineContext, im: Image.Image) -> bool:
    if region.get("kind") != "image_candidate":
        return False
    bbox = region.get("bbox", [])
    if len(bbox) != 4:
        return False
    area_ratio = _bbox_area(bbox) / max(im.width * im.height, 1)
    if area_ratio < 0.25:
        return False
    text_inside = sum(
        1
        for block in ctx.candidates.get("text_blocks", [])
        if _overlap_ratio(block.get("bbox", []), bbox) >= 0.8
    )
    connector_inside = sum(
        1
        for connector in ctx.candidates.get("connectors", [])
        if _connector_bbox_inside(connector, bbox)
    )
    sam3_inside = sum(
        1
        for sam_region in ctx.candidates.get("sam3_regions", [])
        if _overlap_ratio(sam_region.get("bbox", []), bbox) >= 0.8
    )
    # A large region containing many OCR/connector/SAM3 sub-regions is a diagram
    # container, not a bitmap asset.  Keeping it as an image suppresses editable
    # text and makes the output look like a screenshot pasted into PPT.
    return text_inside >= 6 or connector_inside >= 12 or sam3_inside >= 6


def _connector_bbox_inside(connector: dict, bbox: list[float]) -> bool:
    points = connector.get("points")
    if not isinstance(points, list | tuple) or len(points) < 2:
        return False
    try:
        (x1, y1), (x2, y2) = points[:2]
    except (TypeError, ValueError):
        return False
    connector_bbox = [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
    return _overlap_ratio(connector_bbox, bbox) >= 0.8


def _bbox_area(bbox: list[float]) -> float:
    if len(bbox) != 4:
        return 0.0
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _is_covered_by_region(bbox: list[float], regions: list[dict], min_ratio: float) -> bool:
    return any(_overlap_ratio(bbox, region["bbox"]) >= min_ratio for region in regions)


def _overlap_ratio(a: list[float], b: list[float]) -> float:
    if len(a) != 4 or len(b) != 4:
        return 0.0
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area = _bbox_area(a)
    return inter / area if area else 0.0


def _start_asset_manifest(ctx: PipelineContext, asset_root, image_regions: list[dict]) -> dict:
    return {
        "job_id": getattr(ctx, "job_id", None),
        "asset_root": str(asset_root),
        "candidate_count": len(image_regions),
        "items": [],
    }


def _record_asset_manifest_item(
    manifest: dict,
    region: dict,
    status: str,
    asset: dict | None = None,
    element_type: str | None = None,
) -> None:
    item = {
        "id": region.get("id"),
        "source_kind": region.get("kind"),
        "source": region.get("source"),
        "confidence": region.get("confidence"),
        "status": status,
        "source_bbox": region.get("bbox"),
        "has_mask": bool(region.get("mask")),
        "has_polygon": bool(region.get("polygon")),
        "mask_source": _mask_source(region),
    }
    if asset:
        item.update(
            {
                "asset_kind": asset["kind"],
                "asset_path": str(asset["path"]),
                "bounded_bbox": asset["bbox"],
                "element_type": element_type,
                "crop_strategy": asset.get("crop_strategy", "bbox"),
                "alpha_applied": bool(asset.get("alpha_applied")),
                "mask_source": asset.get("mask_source") or _mask_source(region),
            }
        )
    manifest["items"].append(item)


def _write_asset_manifest(ctx: PipelineContext, asset_root, manifest: dict) -> None:
    manifest_path = asset_root / "image_assets.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if hasattr(ctx, "artifacts") and isinstance(ctx.artifacts, dict):
        ctx.artifacts["image_assets"] = manifest_path
    _print_asset_event("manifest", f"path={manifest_path} items={len(manifest['items'])}")


def _print_asset_event(stage: str, message: str) -> None:
    print(f"[image2pptx][assets][{stage}] {message}")


def _prepare_image_asset(
    im: Image.Image, region: dict, asset_root, ctx: PipelineContext | None = None
) -> dict | None:
    crop_box = _bounded_crop_box(region.get("bbox", []), im.width, im.height)
    if crop_box is None:
        return None
    kind = _asset_kind(region, crop_box, im.width, im.height)
    asset_dir = asset_root / _asset_subdir(kind)
    asset_dir.mkdir(parents=True, exist_ok=True)
    asset_path = asset_dir / f"{_safe_asset_name(region.get('id', kind))}.png"
    cropped = im.crop(crop_box).convert("RGBA")
    alpha_mask, mask_source = _asset_alpha_mask(region, crop_box, im.size, cropped.size)
    if alpha_mask is None and _should_require_rmbg_alpha(kind, ctx):
        alpha_mask, mask_source = _rmbg_alpha_from_model(cropped, ctx)
    if alpha_mask is not None:
        cropped.putalpha(alpha_mask)
    cropped.save(asset_path)
    return {
        "kind": kind,
        "path": asset_path,
        "bbox": list(crop_box),
        "crop_strategy": "mask_alpha" if alpha_mask is not None else "bbox",
        "alpha_applied": alpha_mask is not None,
        "mask_source": mask_source,
    }


def _asset_alpha_mask(
    region: dict, crop_box: tuple[int, int, int, int], image_size: tuple[int, int], crop_size: tuple[int, int]
) -> tuple[Image.Image | None, str | None]:
    mask = _decode_region_mask(region.get("mask"), image_size)
    if mask is not None:
        return mask.crop(crop_box).resize(crop_size), _mask_source(region) or "region_mask"
    polygon = region.get("polygon")
    if isinstance(polygon, list) and polygon:
        x1, y1, _x2, _y2 = crop_box
        alpha = Image.new("L", crop_size, 0)
        draw = ImageDraw.Draw(alpha)
        points = [(float(point[0]) - x1, float(point[1]) - y1) for point in polygon if len(point) >= 2]
        if len(points) >= 3:
            draw.polygon(points, fill=255)
            return alpha, "polygon"
    return None, None


def _decode_region_mask(mask: object, image_size: tuple[int, int]) -> Image.Image | None:
    if not isinstance(mask, dict):
        return None
    fmt = mask.get("format")
    data = mask.get("data")
    shape = mask.get("shape")
    if fmt == "png" and isinstance(data, str):
        raw = base64.b64decode(data)
        return Image.open(io.BytesIO(raw)).convert("L").resize(image_size)
    if fmt == "rle" and isinstance(data, str) and isinstance(shape, list) and len(shape) >= 2:
        height, width = int(shape[0]), int(shape[1])
        values: list[int] = []
        current = 0
        for run in data.split(","):
            if not run:
                continue
            length = int(run)
            values.extend([current] * length)
            current = 255 if current == 0 else 0
        expected = width * height
        values = (values + [0] * expected)[:expected]
        return Image.frombytes("L", (width, height), bytes(values)).resize(image_size)
    return None


def _should_require_rmbg_alpha(kind: str, ctx: PipelineContext | None) -> bool:
    if kind not in {"logo", "icon"} or ctx is None or not hasattr(ctx, "settings"):
        return False
    pipeline_enabled = bool(getattr(ctx.settings.pipeline, "enable_rmbg", True))
    model_config = getattr(ctx.settings.models, "rmbg", {})
    model_enabled = bool(model_config.get("enabled", True)) if isinstance(model_config, dict) else True
    return pipeline_enabled and model_enabled


def _rmbg_alpha_from_model(
    cropped: Image.Image, ctx: PipelineContext | None
) -> tuple[Image.Image | None, str | None]:
    if ctx is not None and hasattr(ctx, "settings"):
        model_config = getattr(ctx.settings.models, "rmbg", {})
        if isinstance(model_config, dict):
            adapter = RmbgAdapter(model_config, getattr(ctx, "device", "cpu"))
            alpha, warnings = adapter.infer_alpha(cropped)
            if alpha is not None:
                return alpha, "rmbg_model"
            if warnings:
                ctx.candidates.setdefault("rmbg_warnings", []).extend(warnings)
                raise PipelineStageError(format_stage_failure("rmbg", warnings))
    return None, None


def _mask_source(region: dict) -> str | None:
    if region.get("mask"):
        return "sam3_mask" if region.get("source") == "sam3" else "region_mask"
    if region.get("polygon"):
        return "polygon"
    return None


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


def _asset_element_type(kind: str) -> ElementType:
    if kind == "logo":
        return ElementType.LOGO
    if kind == "icon":
        return ElementType.ICON
    return ElementType.IMAGE


def _asset_subdir(kind: str) -> str:
    if kind == "logo":
        return "logos"
    if kind == "icon":
        return "icons"
    return "images"


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
    if "icon" in label:
        return "icon"
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
