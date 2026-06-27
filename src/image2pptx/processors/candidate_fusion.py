from __future__ import annotations

import json
import re
import base64
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter
from image2pptx.ir.elements import (
    EditableStrategy,
    ElementStyle,
    ElementType,
    Provenance,
    Rect,
    SlideElement,
)
from image2pptx.ir.slide_ir import SlideIR
from image2pptx.ir.candidates import ElementGroup, build_element_groups, grouped_candidates
from image2pptx.models.rmbg import RmbgAdapter
from image2pptx.core.errors import PipelineStageError, format_stage_failure
from image2pptx.pipeline.context import PipelineContext


class CandidateFusionProcessor:
    def run(self, ctx: PipelineContext) -> SlideIR:
        im = Image.open(ctx.artifacts["normalized"])
        slide = SlideIR(width=im.width, height=im.height)
        layers = (
            ctx.candidates.get("layers") if isinstance(ctx.candidates.get("layers"), dict) else {}
        )
        element_groups = _element_groups_for_fusion(ctx, layers)
        layout_regions = ctx.candidates.get("layout_regions", [])
        table_regions = (
            grouped_candidates(element_groups, ElementGroup.TABLE)
            if element_groups
            else [r for r in layout_regions if r.get("kind") == "table_candidate"]
        )
        image_regions = (
            grouped_candidates(element_groups, ElementGroup.ASSET)
            if element_groups
            else [
                r
                for r in layout_regions
                if r.get("kind") in {"image_candidate", "logo_candidate", "icon_candidate"}
            ]
        )
        asset_image_regions, structural_image_regions = _split_asset_image_regions(
            ctx, image_regions, im
        )
        formula_regions = (
            grouped_candidates(element_groups, ElementGroup.FORMULA)
            if element_groups
            else ctx.candidates.get("formulas", [])
        )
        chart_regions = (
            grouped_candidates(element_groups, ElementGroup.CHART)
            if element_groups
            else ctx.candidates.get("charts", [])
        )
        asset_root = ctx.job_dir / "assets"
        asset_root.mkdir(parents=True, exist_ok=True)
        background_asset = _prepare_background_asset(im, asset_root)
        slide.elements.append(
            SlideElement(
                id="background",
                type=ElementType.BACKGROUND,
                bbox=Rect(x=0, y=0, width=im.width, height=im.height),
                z_index=0,
                style=ElementStyle(fill_color="#ffffff"),
                provenance=Provenance(
                    source="background_processor",
                    raw={"background_strategy": "source_raster_underlay"},
                ),
                editable_strategy=EditableStrategy.RASTER_IMAGE,
                asset_path=background_asset,
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
        text_source = (
            grouped_candidates(element_groups, ElementGroup.TEXT)
            if element_groups
            else (
                list(layers.get("texts", []))
                if layers
                else (ctx.candidates.get("text_blocks") or ctx.candidates.get("text", []))
            )
        )
        text_candidates = _split_text_candidates_for_layout(text_source)
        base_shapes = (
            grouped_candidates(element_groups, ElementGroup.CONTAINER)
            if element_groups
            else (
                list(layers.get("containers", []))
                if layers
                else ctx.candidates.get("shapes", [])
            )
        )
        shape_candidates = list(base_shapes)
        _add_container_underlays(slide, im, shape_candidates, asset_root)
        for s in shape_candidates:
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
                        fill_color=(s.get("style") or {}).get("fill_color", s.get("fill_color")),
                        line_color=(s.get("style") or {}).get(
                            "line_color", s.get("line_color", "#666666")
                        ),
                        line_width=float(
                            (s.get("style") or {}).get("line_width", s.get("line_width", 1.0))
                        ),
                        shape_type=s.get("kind"),
                    ),
                    confidence=s["confidence"],
                    provenance=Provenance(source="opencv", raw=s),
                    editable_strategy=EditableStrategy.NATIVE_SHAPE,
                )
            )
        for t in text_candidates:
            if _is_covered_by_region(t["bbox"], table_regions + formula_regions, min_ratio=0.8):
                continue
            if _is_covered_by_region(t["bbox"], asset_image_regions, min_ratio=0.6):
                continue
            x1, y1, x2, y2 = t["bbox"]
            style = _text_style_for_block(t, shape_candidates)
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
        connector_source = (
            grouped_candidates(element_groups, ElementGroup.CONNECTOR)
            if element_groups
            else (
                list(layers.get("connectors", []))
                if layers
                else ctx.candidates.get("connectors", [])
            )
        )
        for c in _semantic_connectors(connector_source, shape_candidates, text_candidates, im)[:35]:
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


def _element_groups_for_fusion(ctx: PipelineContext, layers: dict) -> dict:
    element_groups = ctx.candidates.get("element_groups")
    if isinstance(element_groups, dict) and element_groups:
        return element_groups
    if layers:
        element_groups = build_element_groups(layers, ctx.candidates)
        ctx.candidates["element_groups"] = element_groups
        return element_groups
    return {}


def _prepare_background_asset(im: Image.Image, asset_root) -> Path:
    background_dir = asset_root / "backgrounds"
    background_dir.mkdir(parents=True, exist_ok=True)
    background_path = background_dir / "background_underlay.png"
    # Use a high-fidelity source underlay instead of an aggressively blurred wash.
    # The editable native layers remain on top, while the source underlay preserves
    # complex slide texture, panel boundaries, shadows, and small decorative marks
    # that the current native reconstruction cannot reliably reproduce yet.
    underlay = im.convert("RGB")
    underlay.save(background_path)
    return background_path



def _add_container_underlays(
    slide: SlideIR, im: Image.Image, shape_candidates: list[dict], asset_root: Path
) -> None:
    underlay_dir = asset_root / "container_underlays"
    for index, candidate in enumerate(shape_candidates):
        if not _should_add_container_underlay(candidate):
            continue
        bbox = _bounded_bbox(candidate.get("bbox", []), im.width, im.height)
        if not bbox:
            continue
        x1, y1, x2, y2 = bbox
        if (x2 - x1) * (y2 - y1) <= 0:
            continue
        underlay_dir.mkdir(parents=True, exist_ok=True)
        path = underlay_dir / f"{_safe_asset_name(candidate.get('id') or f'container_{index}')}.png"
        im.crop((int(x1), int(y1), int(x2), int(y2))).save(path)
        slide.elements.append(
            SlideElement(
                id=f"{candidate.get('id', f'container_{index}')}_underlay",
                type=ElementType.UNKNOWN_PATCH,
                bbox=Rect(x=x1, y=y1, width=x2 - x1, height=y2 - y1),
                z_index=6,
                confidence=float(candidate.get("confidence", 0.5)),
                provenance=Provenance(
                    source="container_underlay",
                    raw={"container": candidate, "asset_path": str(path)},
                ),
                editable_strategy=EditableStrategy.RESIDUAL_PATCH,
                asset_path=path,
            )
        )


def _should_add_container_underlay(candidate: dict) -> bool:
    kind = str(candidate.get("kind") or candidate.get("semantic_type") or "").lower()
    source = str(candidate.get("source") or "").lower()
    bbox = candidate.get("bbox", [])
    if len(bbox) != 4:
        return False
    if kind in {"image_candidate", "panel", "card", "group", "container"}:
        return True
    return source in {"layout", "layout_model", "sam3"} and bool(candidate.get("source_id"))


def _bounded_bbox(bbox: list[float], width: int, height: int) -> list[float] | None:
    if len(bbox) != 4:
        return None
    x1 = max(0.0, min(float(width), float(bbox[0])))
    y1 = max(0.0, min(float(height), float(bbox[1])))
    x2 = max(0.0, min(float(width), float(bbox[2])))
    y2 = max(0.0, min(float(height), float(bbox[3])))
    if x2 <= x1 or y2 <= y1:
        return None
    return [x1, y1, x2, y2]


def _safe_asset_name(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("_") or "asset"

def _split_text_candidates_for_layout(text_candidates: list[dict]) -> list[dict]:
    split: list[dict] = []
    for block in text_candidates:
        pieces = _split_text_block_by_raw_items(block)
        for piece in pieces:
            piece = dict(piece)
            piece["id"] = f"text_block_{len(split)}"
            split.append(piece)
    return split


def _split_text_block_by_raw_items(block: dict) -> list[dict]:
    raw_items = block.get("raw_items") or []
    if len(raw_items) <= 1:
        return [block]
    ordered = sorted(
        [item for item in raw_items if len(item.get("bbox", [])) == 4],
        key=lambda item: item["bbox"][0],
    )
    if len(ordered) <= 1:
        return [block]
    heights = [item["bbox"][3] - item["bbox"][1] for item in ordered]
    typical_height = sum(heights) / max(len(heights), 1)
    groups: list[list[dict]] = [[ordered[0]]]
    for item in ordered[1:]:
        previous = groups[-1][-1]
        gap = item["bbox"][0] - previous["bbox"][2]
        if gap > max(typical_height * 1.4, 10):
            groups.append([item])
        else:
            groups[-1].append(item)
    if len(groups) == 1:
        return [block]
    return [_merge_raw_text_group(block, group) for group in groups]


def _merge_raw_text_group(source_block: dict, group: list[dict]) -> dict:
    bbox = _union_bbox([item["bbox"] for item in group])
    return {
        **source_block,
        "text": " ".join(str(item.get("text", "")).strip() for item in group if item.get("text")),
        "bbox": bbox,
        "confidence": sum(float(item.get("confidence", 0.0)) for item in group)
        / max(len(group), 1),
        "source_ids": [item.get("id", "text") for item in group],
        "raw_items": group,
    }


def _text_style_for_block(block: dict, shapes: list[dict]) -> ElementStyle:
    bbox = block.get("bbox", [])
    font_size = block.get("font_size")
    bold = False
    font_color = block.get("font_color") or "#17233a"
    align = block.get("align") or "left"
    if block.get("kind") == "title" or block.get("text_role") == "title":
        font_size = max(18, (bbox[3] - bbox[1]) * 0.55) if len(bbox) == 4 else 18
        bold = True
    container = _best_containing_shape(bbox, shapes)
    if container:
        fill = str(container.get("fill_color") or "#ffffff")
        if _hex_luminance(fill) < 95:
            font_color = "#ffffff"
            bold = True
        elif container.get("kind") == "roundRect":
            font_color = "#17314d"
        align = (
            "center" if _bbox_area(bbox) < _bbox_area(container.get("bbox", [])) * 0.35 else "left"
        )
    return ElementStyle(font_size=font_size, bold=bold, font_color=font_color, align=align)


def _semantic_connectors(
    connectors: list[dict], shapes: list[dict], text_candidates: list[dict], im: Image.Image
) -> list[dict]:
    filtered = []
    for connector in connectors:
        if _is_decorative_connector(connector, shapes, text_candidates, im):
            continue
        filtered.append(connector)
    return filtered


def _is_decorative_connector(
    connector: dict, shapes: list[dict], text_candidates: list[dict], im: Image.Image
) -> bool:
    points = connector.get("points")
    if not isinstance(points, list | tuple) or len(points) < 2:
        return True
    try:
        (x1, y1), (x2, y2) = points[:2]
    except (TypeError, ValueError):
        return True
    dx = abs(float(x2) - float(x1))
    dy = abs(float(y2) - float(y1))
    near_horizontal = dy <= 3
    near_vertical = dx <= 3
    bbox = _padded_line_bbox(float(x1), float(y1), float(x2), float(y2), pad=3)
    if near_horizontal and dx >= im.width * 0.18:
        return True
    if near_vertical and dy >= im.height * 0.18:
        return True
    if any(_overlap_ratio(bbox, block.get("bbox", [])) > 0.25 for block in text_candidates):
        return True
    if any(
        _line_near_shape_edge((float(x1), float(y1), float(x2), float(y2)), shape.get("bbox", []))
        for shape in shapes
    ):
        return True
    return False


def _padded_line_bbox(x1: float, y1: float, x2: float, y2: float, pad: float) -> list[float]:
    return [min(x1, x2) - pad, min(y1, y2) - pad, max(x1, x2) + pad, max(y1, y2) + pad]


def _line_near_shape_edge(line: tuple[float, float, float, float], bbox: list[float]) -> bool:
    if len(bbox) != 4:
        return False
    x1, y1, x2, y2 = line
    bx1, by1, bx2, by2 = bbox
    if abs(y2 - y1) <= 3:
        y = (y1 + y2) / 2
        lx1, lx2 = sorted((x1, x2))
        return min(lx2, bx2) - max(lx1, bx1) > 0 and (abs(y - by1) <= 5 or abs(y - by2) <= 5)
    if abs(x2 - x1) <= 3:
        x = (x1 + x2) / 2
        ly1, ly2 = sorted((y1, y2))
        return min(ly2, by2) - max(ly1, by1) > 0 and (abs(x - bx1) <= 5 or abs(x - bx2) <= 5)
    return False


def _best_containing_shape(bbox: list[float], shapes: list[dict]) -> dict | None:
    if len(bbox) != 4:
        return None
    containers = [shape for shape in shapes if _overlap_ratio(bbox, shape.get("bbox", [])) >= 0.85]
    return min(containers, key=lambda shape: _bbox_area(shape.get("bbox", [])), default=None)


def _hex_luminance(value: str) -> float:
    value = value.lstrip("#")
    if len(value) != 6:
        return 255.0
    r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _expanded_bbox(
    bbox: list[float], pad_x: float, pad_y: float, width: int, height: int
) -> list[float]:
    if len(bbox) != 4:
        return [0.0, 0.0, 0.0, 0.0]
    return [
        max(0.0, bbox[0] - pad_x),
        max(0.0, bbox[1] - pad_y),
        min(float(width), bbox[2] + pad_x),
        min(float(height), bbox[3] + pad_y),
    ]


def _union_bbox(bboxes: list[list[float]]) -> list[float]:
    return [
        min(bbox[0] for bbox in bboxes),
        min(bbox[1] for bbox in bboxes),
        max(bbox[2] for bbox in bboxes),
        max(bbox[3] for bbox in bboxes),
    ]


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
    if area_ratio < 0.08:
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
    # A region containing many OCR/connector/SAM3 sub-regions is a diagram/card
    # container, not a bitmap asset. Keeping it as an image preserves the original
    # icon/text pixels and then overlays extracted icon/text again, causing the
    # duplicated middle-card content seen in generated PPT previews.
    if area_ratio >= 0.25:
        return text_inside >= 6 or connector_inside >= 12 or sam3_inside >= 6
    return text_inside >= 3 or connector_inside >= 6 or sam3_inside >= 3


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
        alpha_mask = _smooth_alpha_mask(alpha_mask)
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


def _smooth_alpha_mask(alpha: Image.Image) -> Image.Image:
    # SAM/RLE/polygon masks are often hard-edged at crop scale. A tiny blur keeps
    # circular icons from looking jagged while preserving the object silhouette.
    return alpha.convert("L").filter(ImageFilter.GaussianBlur(radius=0.6))


def _asset_alpha_mask(
    region: dict,
    crop_box: tuple[int, int, int, int],
    image_size: tuple[int, int],
    crop_size: tuple[int, int],
) -> tuple[Image.Image | None, str | None]:
    mask = _decode_region_mask(region.get("mask"), image_size)
    if mask is not None:
        return mask.crop(crop_box).resize(crop_size), _mask_source(region) or "region_mask"
    polygon = region.get("polygon")
    if isinstance(polygon, list) and polygon:
        x1, y1, _x2, _y2 = crop_box
        alpha = Image.new("L", crop_size, 0)
        draw = ImageDraw.Draw(alpha)
        points = [
            (float(point[0]) - x1, float(point[1]) - y1) for point in polygon if len(point) >= 2
        ]
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
    model_enabled = (
        bool(model_config.get("enabled", True)) if isinstance(model_config, dict) else True
    )
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
