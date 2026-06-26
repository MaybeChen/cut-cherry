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
            slide_size = (im.width, im.height)
        layers = build_layers(ctx.candidates, slide_size)
        ctx.candidates["layers"] = layers
        report_path = ctx.job_dir / "layer_decomposition.json"
        report_path.write_text(json.dumps(layers, ensure_ascii=False, indent=2), encoding="utf-8")
        ctx.artifacts["layer_decomposition"] = report_path


def build_layers(candidates: dict[str, Any], slide_size: tuple[int, int]) -> dict[str, Any]:
    layout_regions = [dict(region) for region in candidates.get("layout_regions", [])]
    text_regions = [dict(text) for text in candidates.get("text_blocks") or candidates.get("text", [])]
    shape_regions = [dict(shape) for shape in candidates.get("shapes", [])]
    connector_regions = [dict(connector) for connector in candidates.get("connectors", [])]
    containers = _container_regions(layout_regions, shape_regions, text_regions, connector_regions, slide_size)
    assets = _asset_regions(layout_regions, containers)
    texts = [_with_parent(text, containers) for text in text_regions]
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
) -> list[dict]:
    containers: list[dict] = []
    for shape in shape_regions:
        if len(shape.get("bbox", [])) != 4:
            continue
        containers.append(_normalize_container(shape, source=shape.get("source", "geometry")))
    for region in layout_regions:
        if not _is_structural_image_container(region, text_regions, connector_regions, slide_size):
            continue
        containers.append(_normalize_container(region, source=region.get("source", "layout")))
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


def _normalize_container(region: dict, source: str) -> dict:
    bbox = [float(value) for value in region.get("bbox", [])]
    fill_color = region.get("fill_color") or _default_container_fill(region)
    return {
        "id": f"container_{region.get('id', len(str(region)))}",
        "kind": region.get("shape_type") or region.get("kind") or "roundRect",
        "bbox": bbox,
        "fill_color": fill_color,
        "line_color": region.get("line_color", "#d7e4f2"),
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
