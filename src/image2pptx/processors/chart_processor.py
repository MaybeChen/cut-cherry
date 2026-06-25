from __future__ import annotations

from image2pptx.pipeline.context import PipelineContext


class ChartProcessor:
    """Detect simple bar-chart candidates from rectangle shape candidates."""

    def run(self, ctx: PipelineContext) -> None:
        bars = [_normalize_bar(shape) for shape in ctx.candidates.get("shapes", [])]
        bars = [bar for bar in bars if bar and _is_bar_like(bar)]
        groups = _group_bottom_aligned_bars(bars)
        charts = []
        for group in groups:
            if len(group) < 3:
                continue
            group = sorted(group, key=lambda bar: bar["bbox"][0])
            bbox = _union_bbox([bar["bbox"] for bar in group])
            max_height = max(bar["height"] for bar in group) or 1.0
            charts.append(
                {
                    "id": f"chart_{len(charts)}",
                    "kind": "bar_chart",
                    "bbox": bbox,
                    "confidence": 0.55 + min(len(group), 5) * 0.05,
                    "categories": [f"{index + 1}" for index in range(len(group))],
                    "values": [round(bar["height"] / max_height, 3) for bar in group],
                    "source_ids": [bar["id"] for bar in group],
                }
            )
        ctx.candidates["charts"] = charts


class TODOProcessor(ChartProcessor):
    """Backward-compatible alias for the old extension-point class name."""


def _normalize_bar(shape: dict) -> dict | None:
    bbox = shape.get("bbox")
    if not bbox or len(bbox) != 4:
        return None
    x1, y1, x2, y2 = [float(value) for value in bbox]
    width = max(0.0, x2 - x1)
    height = max(0.0, y2 - y1)
    return {
        "id": shape.get("id", "shape"),
        "bbox": [x1, y1, x2, y2],
        "width": width,
        "height": height,
        "bottom": y2,
    }


def _is_bar_like(bar: dict) -> bool:
    if bar["width"] < 6 or bar["height"] < 20:
        return False
    return 0.15 <= bar["width"] / max(bar["height"], 1.0) <= 1.4


def _group_bottom_aligned_bars(bars: list[dict]) -> list[list[dict]]:
    groups: list[list[dict]] = []
    for bar in sorted(bars, key=lambda item: item["bottom"]):
        for group in groups:
            typical_height = sum(item["height"] for item in group) / len(group)
            tolerance = max(8.0, typical_height * 0.18)
            if abs(bar["bottom"] - group[0]["bottom"]) <= tolerance:
                group.append(bar)
                break
        else:
            groups.append([bar])
    return groups


def _union_bbox(bboxes: list[list[float]]) -> list[float]:
    return [
        min(bbox[0] for bbox in bboxes),
        min(bbox[1] for bbox in bboxes),
        max(bbox[2] for bbox in bboxes),
        max(bbox[3] for bbox in bboxes),
    ]
