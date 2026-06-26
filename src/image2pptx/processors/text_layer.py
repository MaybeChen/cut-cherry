from __future__ import annotations

import json
from typing import Any

from PIL import Image

from image2pptx.pipeline.context import PipelineContext


class TextLayerProcessor:
    """Normalize OCR/layout text into a style-aware TextLayer.

    OCR gives coordinates and content; this processor adds the minimum metadata
    needed by layered reconstruction: role, estimated font size, sampled font
    color and alignment.  It deliberately keeps the original bbox as the source
    of truth instead of letting a model invent coordinates.
    """

    def run(self, ctx: PipelineContext) -> None:
        blocks = [dict(block) for block in (ctx.candidates.get("text_blocks") or ctx.candidates.get("text", []))]
        with Image.open(ctx.artifacts["normalized"]) as image:
            text_layer = build_text_layer(blocks, image.convert("RGB"))
        ctx.candidates["text_layer"] = text_layer
        report_path = ctx.job_dir / "text_layer.json"
        report_path.write_text(json.dumps(text_layer, ensure_ascii=False, indent=2), encoding="utf-8")
        ctx.artifacts["text_layer"] = report_path


def build_text_layer(blocks: list[dict[str, Any]], image: Image.Image) -> list[dict[str, Any]]:
    slide_width, slide_height = image.size
    enriched: list[dict[str, Any]] = []
    for index, block in enumerate(blocks):
        bbox = [float(value) for value in block.get("bbox", [])]
        if len(bbox) != 4:
            continue
        text = str(block.get("text", "")).strip()
        if not text:
            continue
        item = dict(block)
        item.setdefault("id", f"text_layer_{index}")
        item["bbox"] = bbox
        item["text_role"] = _infer_text_role(text, bbox, slide_width, slide_height)
        item["font_size"] = _estimate_font_size(bbox, item["text_role"])
        item["font_color"] = _sample_text_color(image, bbox)
        item["align"] = _infer_alignment(bbox, slide_width)
        item["layer_kind"] = "text"
        enriched.append(item)
    return _dedupe_texts(enriched)


def _infer_text_role(text: str, bbox: list[float], slide_width: int, slide_height: int) -> str:
    height = bbox[3] - bbox[1]
    width = bbox[2] - bbox[0]
    if bbox[1] < slide_height * 0.16 and height >= 18 and width > slide_width * 0.35:
        return "title"
    if bbox[1] < slide_height * 0.18:
        return "subtitle"
    if len(text) <= 28 and height <= 18:
        return "label"
    return "body"


def _estimate_font_size(bbox: list[float], role: str) -> float:
    height = max(8.0, bbox[3] - bbox[1])
    multiplier = {"title": 0.72, "subtitle": 0.66, "label": 0.62, "body": 0.58}.get(role, 0.58)
    return round(max(7.0, min(28.0, height * multiplier)), 2)


def _infer_alignment(bbox: list[float], slide_width: int) -> str:
    center = (bbox[0] + bbox[2]) / 2
    if slide_width * 0.25 <= center <= slide_width * 0.75:
        return "center"
    return "left"


def _sample_text_color(image: Image.Image, bbox: list[float]) -> str:
    x1, y1, x2, y2 = _clamp_bbox(bbox, image.size)
    if x2 <= x1 or y2 <= y1:
        return "#17233a"
    pixels = list(_pixel_data(image.crop((x1, y1, x2, y2))))
    # Text pixels are usually high-contrast extremes. Prefer dark foreground;
    # for dark containers, prefer light foreground pixels.
    dark = [pixel for pixel in pixels if _luminance(pixel) < 115]
    light = [pixel for pixel in pixels if _luminance(pixel) > 205]
    chosen = dark if len(dark) >= max(3, len(light) // 2) else light
    if not chosen:
        return "#17233a"
    r = int(sum(pixel[0] for pixel in chosen) / len(chosen))
    g = int(sum(pixel[1] for pixel in chosen) / len(chosen))
    b = int(sum(pixel[2] for pixel in chosen) / len(chosen))
    return f"#{r:02x}{g:02x}{b:02x}"


def _clamp_bbox(bbox: list[float], size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = size
    x1 = max(0, min(width, int(bbox[0])))
    y1 = max(0, min(height, int(bbox[1])))
    x2 = max(0, min(width, int(bbox[2])))
    y2 = max(0, min(height, int(bbox[3])))
    return x1, y1, x2, y2


def _luminance(pixel: tuple[int, int, int]) -> float:
    return pixel[0] * 0.299 + pixel[1] * 0.587 + pixel[2] * 0.114


def _dedupe_texts(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    for block in sorted(blocks, key=lambda item: (item["bbox"][1], item["bbox"][0])):
        if any(_overlap_ratio(block["bbox"], existing["bbox"]) > 0.92 and block.get("text") == existing.get("text") for existing in deduped):
            continue
        deduped.append(block)
    return deduped


def _overlap_ratio(a: list[float], b: list[float]) -> float:
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    return inter / area if area else 0.0


def _pixel_data(image: Image.Image):
    if hasattr(image, "get_flattened_data"):
        return image.get_flattened_data()
    return image.getdata()
