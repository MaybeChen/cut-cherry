from __future__ import annotations

import cv2
import numpy as np

from image2pptx.pipeline.context import PipelineContext


class GeometryProcessor:
    def run(self, ctx: PipelineContext) -> None:
        img = cv2.imread(str(ctx.artifacts["normalized"]))
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        h, w = gray.shape
        shapes = _detect_shapes(img, edges, w, h)
        lines = _detect_lines(edges, shapes, w, h)
        ctx.candidates["shapes"] = shapes
        ctx.candidates["lines"] = lines


def _detect_shapes(img: np.ndarray, edges: np.ndarray, width: int, height: int) -> list[dict]:
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    shapes: list[dict] = []
    seen: list[list[float]] = []
    slide_area = width * height
    sorted_contours = sorted(contours, key=cv2.contourArea, reverse=True)
    for contour in sorted_contours[:500]:
        area = cv2.contourArea(contour)
        if area < 250 or area > slide_area * 0.92:
            continue
        x, y, bw, bh = cv2.boundingRect(contour)
        if bw < 20 or bh < 14:
            continue
        if bw / max(bh, 1) > 35 or bh / max(bw, 1) > 20:
            continue
        bbox = [float(x), float(y), float(x + bw), float(y + bh)]
        if any(_overlap_ratio(bbox, old) > 0.92 for old in seen):
            continue
        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue
        approx = cv2.approxPolyDP(contour, 0.03 * perimeter, True)
        extent = area / max(bw * bh, 1)
        area_ratio = (bw * bh) / max(slide_area, 1)
        if len(approx) < 4 or extent < 0.18:
            continue
        crop = img[y : y + bh, x : x + bw]
        fill_color = _representative_fill_color(crop)
        shape_type = "roundRect" if _looks_like_card(bbox, (width, height), area_ratio) else "rectangle"
        shapes.append(
            {
                "id": f"shape_{len(shapes)}",
                "kind": shape_type,
                "bbox": bbox,
                "fill_color": fill_color,
                "line_color": "#b7cde2" if shape_type == "roundRect" else "#666666",
                "confidence": 0.72 if shape_type == "roundRect" else 0.62,
                "source": "opencv_contour",
            }
        )
        seen.append(bbox)
        if len(shapes) >= 80:
            break
    return shapes


def _detect_lines(edges: np.ndarray, shapes: list[dict], width: int, height: int) -> list[dict]:
    raw = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80, minLineLength=40, maxLineGap=8)
    if raw is None:
        return []
    lines: list[dict] = []
    for candidate in raw[:240]:
        x1, y1, x2, y2 = map(int, candidate[0])
        if _should_drop_line((x1, y1, x2, y2), shapes, width, height):
            continue
        lines.append({"id": f"line_{len(lines)}", "points": [[x1, y1], [x2, y2]], "confidence": 0.6})
        if len(lines) >= 60:
            break
    return lines


def _should_drop_line(line: tuple[int, int, int, int], shapes: list[dict], width: int, height: int) -> bool:
    x1, y1, x2, y2 = line
    dx = abs(x2 - x1)
    dy = abs(y2 - y1)
    length = float((dx * dx + dy * dy) ** 0.5)
    if length < 12:
        return True
    near_horizontal = dy <= 3
    near_vertical = dx <= 3
    # Page/card borders and shadows are not semantic connectors. They produced
    # most of the long blue lines that crossed text in generated slides.
    if near_horizontal and dx >= width * 0.12:
        if min(y1, y2) <= 8 or max(y1, y2) >= height - 8:
            return True
        if any(_line_matches_shape_edge(line, shape.get("bbox", []), "horizontal") for shape in shapes):
            return True
    if near_vertical and dy >= height * 0.12:
        if min(x1, x2) <= 8 or max(x1, x2) >= width - 8:
            return True
        if any(_line_matches_shape_edge(line, shape.get("bbox", []), "vertical") for shape in shapes):
            return True
    # Long perfectly axis-aligned strokes without an arrow head are usually
    # container separators in these slides, not connectors.
    if (near_horizontal and dx >= width * 0.42) or (near_vertical and dy >= height * 0.42):
        return True
    return False


def _line_matches_shape_edge(line: tuple[int, int, int, int], bbox: list[float], orientation: str) -> bool:
    if len(bbox) != 4:
        return False
    x1, y1, x2, y2 = line
    bx1, by1, bx2, by2 = bbox
    if orientation == "horizontal":
        y = (y1 + y2) / 2
        lx1, lx2 = sorted((x1, x2))
        overlaps_x = min(lx2, bx2) - max(lx1, bx1)
        return overlaps_x >= 0.55 * max(lx2 - lx1, 1) and (abs(y - by1) <= 5 or abs(y - by2) <= 5)
    x = (x1 + x2) / 2
    ly1, ly2 = sorted((y1, y2))
    overlaps_y = min(ly2, by2) - max(ly1, by1)
    return overlaps_y >= 0.55 * max(ly2 - ly1, 1) and (abs(x - bx1) <= 5 or abs(x - bx2) <= 5)


def _looks_like_card(bbox: list[float], slide_size: tuple[int, int], area_ratio: float) -> bool:
    width, height = slide_size
    x1, y1, x2, y2 = bbox
    bw = max(0.0, x2 - x1)
    bh = max(0.0, y2 - y1)
    aspect = bw / max(bh, 1.0)
    if area_ratio >= 0.015 and 1.4 <= aspect <= 12 and bh >= height * 0.045:
        return True
    if area_ratio >= 0.035 and 0.35 <= aspect <= 2.8 and bw >= width * 0.08:
        return True
    return False


def _representative_fill_color(crop: np.ndarray) -> str:
    if crop.size == 0:
        return "#ffffff"
    sample = crop.reshape(-1, 3)
    # The median keeps light card fills stable while avoiding dark border pixels.
    color = np.median(sample, axis=0).astype(int)
    return "#%02x%02x%02x" % (color[2], color[1], color[0])


def _overlap_ratio(a: list[float], b: list[float]) -> float:
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    return inter / area if area else 0.0
