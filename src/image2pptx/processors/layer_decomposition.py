from __future__ import annotations

import json
from typing import Any

from PIL import Image

from image2pptx.pipeline.context import PipelineContext


class LayerDecompositionProcessor:
    """Build explicit visual/semantic layers before SlideIR fusion.

    This is the first P0 step toward an Edit-Banana-style layered pipeline: keep
    background, containers/cards, text, visual assets and connectors in separate
    buckets, then assign child elements to their closest container.  Candidate
    fusion can consume this structure instead of flattening every model output at
    once.
    """

    def run(self, ctx: PipelineContext) -> None:
        image_path = ctx.artifacts.get("normalized")
        with Image.open(image_path) as im:
            image = im.convert("RGB")
            slide_size = (image.width, image.height)
            layers = build_layers(ctx.candidates, slide_size, image=image)
        ctx.candidates["layers"] = layers
        report_path = ctx.job_dir / "layer_decomposition.json"
        report_path.write_text(json.dumps(layers, ensure_ascii=False, indent=2), encoding="utf-8")
        ctx.artifacts["layer_decomposition"] = report_path


def build_layers(candidates: dict[str, Any], slide_size: tuple[int, int], image: Image.Image | None = None) -> dict[str, Any]:
    layout_regions = [dict(region) for region in candidates.get("layout_regions", [])]
    sam3_regions = [_normalize_sam3_region(region) for region in candidates.get("sam3_regions", [])]
    visual_regions = _dedupe_visual_regions([*layout_regions, *sam3_regions])
    text_regions = [dict(text) for text in candidates.get("text_layer") or candidates.get("text_blocks") or candidates.get("text", [])]
    shape_regions = [dict(shape) for shape in candidates.get("shapes", [])]
    connector_regions = [dict(connector) for connector in candidates.get("connectors", [])]
    containers = _container_regions(visual_regions, shape_regions, text_regions, connector_regions, slide_size, image)
    assets = _asset_regions(visual_regions, containers)
    texts = [_with_parent(_apply_text_style(text, image), containers) for text in text_regions]
    assets = [_with_parent(asset, containers) for asset in assets]
    connectors = [_with_connector_parent(connector, containers) for connector in connector_regions]
    return {
        "background": {"strategy": "blurred_raster_underlay"},
        "containers": containers,
        "texts": texts,
        "assets": assets,
        "connectors": connectors,
        "counts": {
            "containers": len(containers),
            "texts": len(texts),
            "assets": len(assets),
            "connectors": len(connectors),
        },
    }


def _container_regions(
    layout_regions: list[dict],
    shape_regions: list[dict],
    text_regions: list[dict],
    connector_regions: list[dict],
    slide_size: tuple[int, int],
    image: Image.Image | None = None,
) -> list[dict]:
    containers: list[dict] = []
    for shape in shape_regions:
        if len(shape.get("bbox", [])) != 4:
            continue
        containers.append(_normalize_container(shape, source=shape.get("source", "geometry"), image=image))
    for region in layout_regions:
        if not _is_structural_image_container(region, text_regions, connector_regions, slide_size):
            continue
        containers.append(_normalize_container(region, source=region.get("source", "layout"), image=image))
    return _dedupe_containers(containers)


def _asset_regions(layout_regions: list[dict], containers: list[dict]) -> list[dict]:
    assets = []
    for region in layout_regions:
        if region.get("kind") not in {"image_candidate", "logo_candidate", "icon_candidate"}:
            continue
        if any(region.get("id") == container.get("source_id") for container in containers):
            continue
        assets.append(region)
    return assets


def _normalize_container(region: dict, source: str, image: Image.Image | None = None) -> dict:
    bbox = [float(value) for value in region.get("bbox", [])]
    fill_color = region.get("fill_color") or _sample_fill_color(image, bbox) or _default_container_fill(region)
    style = {
        "fill_color": fill_color,
        "line_color": region.get("line_color", "#d7e4f2"),
        "corner_radius": _estimate_corner_radius(bbox),
        "shadow": _estimate_shadow(region),
    }
    return {
        "id": f"container_{region.get('id', len(str(region)))}",
        "kind": region.get("shape_type") or region.get("kind") or "roundRect",
        "bbox": bbox,
        "fill_color": fill_color,
        "line_color": style["line_color"],
        "style": style,
        "semantic_type": region.get("semantic_type") or _infer_container_semantic_type(region, bbox),
        "confidence": float(region.get("confidence", 0.5)),
        "source": source,
        "source_id": region.get("id"),
    }


def _default_container_fill(region: dict) -> str:
    label = " ".join(str(region.get(key, "")).lower() for key in ("id", "label", "kind", "text"))
    if "implementation" in label or "middle" in label:
        return "#083c5a"
    return "#eef6ff"


def _is_structural_image_container(
    region: dict, text_regions: list[dict], connector_regions: list[dict], slide_size: tuple[int, int]
) -> bool:
    if region.get("kind") != "image_candidate" or len(region.get("bbox", [])) != 4:
        return False
    width, height = slide_size
    bbox = [float(value) for value in region["bbox"]]
    area_ratio = _bbox_area(bbox) / max(width * height, 1)
    if area_ratio < 0.08:
        return False
    text_inside = sum(1 for text in text_regions if _overlap_ratio(text.get("bbox", []), bbox) >= 0.8)
    connector_inside = sum(1 for connector in connector_regions if _connector_inside(connector, bbox))
    if region.get("source") == "sam3" and region.get("has_mask") and area_ratio >= 0.04 and (text_inside >= 2 or connector_inside >= 3):
        return True
    return text_inside >= 3 or connector_inside >= 6


def _with_parent(item: dict, containers: list[dict]) -> dict:
    parent = _best_container(item.get("bbox", []), containers)
    if parent:
        item = dict(item)
        item["parent_id"] = parent["id"]
    return item


def _with_connector_parent(connector: dict, containers: list[dict]) -> dict:
    points = connector.get("points")
    if not isinstance(points, list | tuple) or len(points) < 2:
        return connector
    try:
        (x1, y1), (x2, y2) = points[:2]
    except (TypeError, ValueError):
        return connector
    connector = dict(connector)
    start_parent = _best_container([x1, y1, x1 + 1, y1 + 1], containers)
    end_parent = _best_container([x2, y2, x2 + 1, y2 + 1], containers)
    if start_parent:
        connector["source_container_id"] = start_parent["id"]
    if end_parent:
        connector["target_container_id"] = end_parent["id"]
    return connector


def _best_container(bbox: list[float], containers: list[dict]) -> dict | None:
    if len(bbox) != 4:
        return None
    matches = [container for container in containers if _overlap_ratio(bbox, container.get("bbox", [])) >= 0.75]
    return min(matches, key=lambda container: _bbox_area(container.get("bbox", [])), default=None)


def _dedupe_containers(containers: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    for container in sorted(containers, key=lambda item: _bbox_area(item["bbox"]), reverse=True):
        if any(_overlap_ratio(container["bbox"], existing["bbox"]) > 0.9 for existing in deduped):
            continue
        deduped.append(container)
    return sorted(deduped, key=lambda item: (item["bbox"][1], item["bbox"][0]))


def _connector_inside(connector: dict, bbox: list[float]) -> bool:
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


def _overlap_ratio(a: list[float], b: list[float]) -> float:
    if len(a) != 4 or len(b) != 4:
        return 0.0
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area = _bbox_area(a)
    return inter / area if area else 0.0


def _normalize_sam3_region(region: dict) -> dict:
    normalized = dict(region)
    normalized.setdefault("source", "sam3")
    if normalized.get("id") is None:
        bbox_token = "_".join(str(int(float(value))) for value in normalized.get("bbox", [])[:4]) or "unknown"
        normalized["id"] = f"sam3_{bbox_token}"
    if normalized.get("mask") is not None:
        normalized["has_mask"] = True
    if normalized.get("polygon") is not None:
        normalized["has_polygon"] = True
    label = str(normalized.get("label") or normalized.get("prompt") or normalized.get("kind") or "").lower()
    if "icon" in label or "symbol" in label:
        normalized["kind"] = "icon_candidate"
    elif "logo" in label:
        normalized["kind"] = "logo_candidate"
    else:
        normalized.setdefault("kind", "image_candidate")
    return normalized


def _dedupe_visual_regions(regions: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    for region in sorted(regions, key=lambda item: (_source_priority(item), -float(item.get("confidence", 0.0)))):
        bbox = region.get("bbox", [])
        if len(bbox) != 4:
            continue
        if any(_overlap_ratio(bbox, existing.get("bbox", [])) > 0.88 for existing in deduped):
            continue
        deduped.append(region)
    return deduped


def _source_priority(region: dict) -> int:
    # Prefer SAM3 masks over coarse layout boxes when both describe the same object.
    if region.get("source") == "sam3" or region.get("has_mask"):
        return 0
    return 1


def _apply_text_style(text: dict, image: Image.Image | None) -> dict:
    item = dict(text)
    bbox = item.get("bbox", [])
    item.setdefault("layer_kind", "text")
    item.setdefault("font_size", _estimate_text_font_size(bbox))
    item.setdefault("font_color", _sample_text_color(image, bbox) or "#17233a")
    item.setdefault("align", "center" if item.get("text_role") == "label" else "left")
    return item


def _estimate_text_font_size(bbox: list[float]) -> float:
    if len(bbox) != 4:
        return 10.0
    return round(max(7.0, min(28.0, (bbox[3] - bbox[1]) * 0.62)), 2)


def _sample_text_color(image: Image.Image | None, bbox: list[float]) -> str | None:
    if image is None or len(bbox) != 4:
        return None
    pixels = _crop_pixels(image, bbox)
    if not pixels:
        return None
    dark = [pixel for pixel in pixels if _luminance(pixel) < 120]
    light = [pixel for pixel in pixels if _luminance(pixel) > 210]
    chosen = light if len(light) > len(dark) * 1.5 else dark
    if not chosen:
        return None
    return _avg_hex(chosen)


def _sample_fill_color(image: Image.Image | None, bbox: list[float]) -> str | None:
    if image is None or len(bbox) != 4:
        return None
    x1, y1, x2, y2 = bbox
    inset_x = max(1, int((x2 - x1) * 0.25))
    inset_y = max(1, int((y2 - y1) * 0.25))
    pixels = _crop_pixels(image, [x1 + inset_x, y1 + inset_y, x2 - inset_x, y2 - inset_y])
    if len(pixels) < 3:
        return None
    # Prefer the dominant mid/background color, not black text or white page.
    filtered = [p for p in pixels if 35 < _luminance(p) < 245]
    if not filtered:
        filtered = pixels
    return _avg_hex(filtered[:: max(1, len(filtered) // 300)])


def _crop_pixels(image: Image.Image, bbox: list[float]) -> list[tuple[int, int, int]]:
    width, height = image.size
    x1 = max(0, min(width, int(bbox[0])))
    y1 = max(0, min(height, int(bbox[1])))
    x2 = max(0, min(width, int(bbox[2])))
    y2 = max(0, min(height, int(bbox[3])))
    if x2 <= x1 or y2 <= y1:
        return []
    return list(_pixel_data(image.crop((x1, y1, x2, y2)).convert("RGB")))


def _avg_hex(pixels: list[tuple[int, int, int]]) -> str:
    r = int(sum(pixel[0] for pixel in pixels) / len(pixels))
    g = int(sum(pixel[1] for pixel in pixels) / len(pixels))
    b = int(sum(pixel[2] for pixel in pixels) / len(pixels))
    return f"#{r:02x}{g:02x}{b:02x}"


def _luminance(pixel: tuple[int, int, int]) -> float:
    return pixel[0] * 0.299 + pixel[1] * 0.587 + pixel[2] * 0.114


def _estimate_corner_radius(bbox: list[float]) -> float:
    if len(bbox) != 4:
        return 0.0
    return round(min(18.0, max(4.0, min(bbox[2] - bbox[0], bbox[3] - bbox[1]) * 0.08)), 2)


def _estimate_shadow(region: dict) -> dict | None:
    label = " ".join(str(region.get(key, "")).lower() for key in ("id", "label", "kind", "text"))
    if "implementation" in label or "card" in label or "panel" in label:
        return {"color": "#9fb6cc", "opacity": 0.28, "blur": 8, "offset_x": 0, "offset_y": 3}
    return None


def _infer_container_semantic_type(region: dict, bbox: list[float]) -> str:
    label = " ".join(str(region.get(key, "")).lower() for key in ("id", "label", "kind", "text"))
    if "callout" in label:
        return "callout"
    if "panel" in label or (len(bbox) == 4 and bbox[0] > 0 and (bbox[2] - bbox[0]) < (bbox[3] - bbox[1]) * 1.2):
        return "panel"
    return "container"


def _pixel_data(image: Image.Image):
    if hasattr(image, "get_flattened_data"):
        return image.get_flattened_data()
    return image.getdata()
