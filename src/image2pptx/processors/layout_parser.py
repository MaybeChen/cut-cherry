from __future__ import annotations

from statistics import median

from image2pptx.pipeline.context import PipelineContext


class LayoutParserProcessor:
    """Build lightweight layout blocks from OCR and geometry candidates.

    This rule-based parser is intentionally model-free: it turns raw OCR boxes
    into line/paragraph blocks and marks simple table/image candidates so the
    fusion stage can create fewer, more meaningful SlideIR elements before the
    heavier Phase 2 models are available.
    """

    def run(self, ctx: PipelineContext) -> None:
        text_blocks = _merge_text_into_blocks(ctx.candidates.get("text", []))
        layout_regions = [dict(block) for block in text_blocks]
        layout_regions.extend(
            _detect_table_candidates(ctx.candidates.get("lines", []), text_blocks)
        )
        layout_regions.extend(
            _detect_image_candidates(ctx.candidates.get("shapes", []), text_blocks)
        )
        ctx.candidates["text_blocks"] = text_blocks
        ctx.candidates["layout_regions"] = layout_regions


class TODOProcessor(LayoutParserProcessor):
    """Backward-compatible alias for the old extension-point class name."""


def _merge_text_into_blocks(text_items: list[dict]) -> list[dict]:
    rows = [_normalize_text_item(item) for item in text_items if item.get("text")]
    rows.sort(key=lambda item: (item["bbox"][1], item["bbox"][0]))
    if not rows:
        return []

    heights = [item["bbox"][3] - item["bbox"][1] for item in rows]
    typical_height = median(heights) if heights else 12.0
    line_gap = max(typical_height * 0.65, 6.0)

    lines: list[list[dict]] = []
    for item in rows:
        center_y = (item["bbox"][1] + item["bbox"][3]) / 2
        for line in lines:
            if abs(center_y - _line_center_y(line)) <= line_gap:
                line.append(item)
                break
        else:
            lines.append([item])

    merged_lines = [_merge_line(line, i) for i, line in enumerate(lines)]
    merged_lines.sort(key=lambda item: (item["bbox"][1], item["bbox"][0]))

    blocks: list[dict] = []
    current: list[dict] = []
    for line in merged_lines:
        if not current:
            current = [line]
            continue
        prev = current[-1]
        prev_height = prev["bbox"][3] - prev["bbox"][1]
        vertical_gap = line["bbox"][1] - prev["bbox"][3]
        horizontal_aligned = abs(line["bbox"][0] - prev["bbox"][0]) <= max(prev_height * 1.5, 16)
        if vertical_gap <= max(prev_height * 1.2, 14) and horizontal_aligned:
            current.append(line)
        else:
            blocks.append(_merge_paragraph(current, len(blocks)))
            current = [line]
    if current:
        blocks.append(_merge_paragraph(current, len(blocks)))

    return [_classify_text_block(block) for block in blocks]


def _normalize_text_item(item: dict) -> dict:
    x1, y1, x2, y2 = item["bbox"]
    return {
        "id": item.get("id", "text"),
        "text": str(item.get("text", "")).strip(),
        "bbox": [float(x1), float(y1), float(x2), float(y2)],
        "confidence": float(item.get("confidence", 0.0)),
        "source_ids": [item.get("id", "text")],
        "raw_items": [item],
    }


def _line_center_y(line: list[dict]) -> float:
    ys = [(item["bbox"][1] + item["bbox"][3]) / 2 for item in line]
    return sum(ys) / len(ys)


def _merge_line(line: list[dict], index: int) -> dict:
    ordered = sorted(line, key=lambda item: item["bbox"][0])
    return {
        "id": f"text_line_{index}",
        "kind": "text_line",
        "text": " ".join(item["text"] for item in ordered if item["text"]),
        "bbox": _union_bbox([item["bbox"] for item in ordered]),
        "confidence": _average_confidence(ordered),
        "source_ids": [sid for item in ordered for sid in item["source_ids"]],
        "raw_items": [raw for item in ordered for raw in item["raw_items"]],
    }


def _merge_paragraph(lines: list[dict], index: int) -> dict:
    return {
        "id": f"text_block_{index}",
        "kind": "paragraph",
        "text": "\n".join(line["text"] for line in lines if line["text"]),
        "bbox": _union_bbox([line["bbox"] for line in lines]),
        "confidence": _average_confidence(lines),
        "source_ids": [sid for line in lines for sid in line["source_ids"]],
        "line_count": len(lines),
        "raw_lines": lines,
    }


def _classify_text_block(block: dict) -> dict:
    _x1, y1, _x2, y2 = block["bbox"]
    height = y2 - y1
    text = block.get("text", "")
    if y1 < 120 and block.get("line_count", 1) == 1 and height >= 22:
        block["kind"] = "title"
    elif y1 >= 0.82 * max(y2, 1) and len(text) <= 80:
        block["kind"] = "footer"
    return block


def _detect_table_candidates(
    lines: list[dict], text_blocks: list[dict] | None = None
) -> list[dict]:
    horizontal = []
    vertical = []
    for line in lines:
        points = line.get("points") or []
        if len(points) != 2:
            continue
        (x1, y1), (x2, y2) = points
        if abs(y2 - y1) <= 4 and abs(x2 - x1) >= 40:
            horizontal.append(line)
        elif abs(x2 - x1) <= 4 and abs(y2 - y1) >= 30:
            vertical.append(line)
    if len(horizontal) < 2 or len(vertical) < 2:
        return []

    bboxes = []
    for line in horizontal + vertical:
        (x1, y1), (x2, y2) = line["points"]
        bboxes.append([min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)])
    bbox = _union_bbox(bboxes)
    x_edges = _dedupe_sorted_coords(
        [point[0] for line in vertical for point in line["points"]],
        tolerance=6.0,
    )
    y_edges = _dedupe_sorted_coords(
        [point[1] for line in horizontal for point in line["points"]],
        tolerance=6.0,
    )
    cells = _assign_text_to_cells(text_blocks or [], x_edges, y_edges)
    return [
        {
            "id": "table_candidate_0",
            "kind": "table_candidate",
            "bbox": bbox,
            "confidence": 0.65 if cells else 0.55,
            "source_ids": [line.get("id", "line") for line in horizontal + vertical],
            "x_edges": x_edges,
            "y_edges": y_edges,
            "rows": max(0, len(y_edges) - 1),
            "cols": max(0, len(x_edges) - 1),
            "cells": cells,
        }
    ]


def _detect_image_candidates(shapes: list[dict], text_blocks: list[dict]) -> list[dict]:
    regions = []
    for shape in shapes:
        bbox = [float(value) for value in shape.get("bbox", [])]
        if len(bbox) != 4:
            continue
        x1, y1, x2, y2 = bbox
        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        overlaps_text = any(_overlap_ratio(bbox, block["bbox"]) > 0.2 for block in text_blocks)
        if area >= 20_000 and not overlaps_text:
            regions.append(
                {
                    "id": f"image_candidate_{len(regions)}",
                    "kind": "image_candidate",
                    "bbox": bbox,
                    "confidence": min(float(shape.get("confidence", 0.4)), 0.6),
                    "source_ids": [shape.get("id", "shape")],
                }
            )
    return regions


def _union_bbox(bboxes: list[list[float]]) -> list[float]:
    return [
        min(bbox[0] for bbox in bboxes),
        min(bbox[1] for bbox in bboxes),
        max(bbox[2] for bbox in bboxes),
        max(bbox[3] for bbox in bboxes),
    ]


def _dedupe_sorted_coords(values: list[float], tolerance: float) -> list[float]:
    coords = sorted(float(value) for value in values)
    if not coords:
        return []
    merged = [coords[0]]
    for value in coords[1:]:
        if abs(value - merged[-1]) <= tolerance:
            merged[-1] = (merged[-1] + value) / 2
        else:
            merged.append(value)
    return merged


def _assign_text_to_cells(
    text_blocks: list[dict],
    x_edges: list[float],
    y_edges: list[float],
) -> list[list[dict]]:
    if len(x_edges) < 2 or len(y_edges) < 2:
        return []
    rows: list[list[dict]] = [
        [{} for _ in range(len(x_edges) - 1)] for _ in range(len(y_edges) - 1)
    ]
    for block in text_blocks:
        cx = (block["bbox"][0] + block["bbox"][2]) / 2
        cy = (block["bbox"][1] + block["bbox"][3]) / 2
        col = _find_interval(cx, x_edges)
        row = _find_interval(cy, y_edges)
        if row is None or col is None:
            continue
        cell = rows[row][col]
        existing = cell.get("text")
        cell.update(
            {
                "row": row,
                "col": col,
                "text": f"{existing}\n{block['text']}" if existing else block["text"],
                "source_ids": cell.get("source_ids", []) + block.get("source_ids", [block["id"]]),
            }
        )
    return rows


def _find_interval(value: float, edges: list[float]) -> int | None:
    for index in range(len(edges) - 1):
        if edges[index] <= value <= edges[index + 1]:
            return index
    return None


def _average_confidence(items: list[dict]) -> float:
    if not items:
        return 0.0
    return sum(float(item.get("confidence", 0.0)) for item in items) / len(items)


def _overlap_ratio(a: list[float], b: list[float]) -> float:
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    return inter / area if area else 0.0
