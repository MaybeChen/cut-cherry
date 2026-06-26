from __future__ import annotations

from typing import Any

from lxml import html

from image2pptx.pipeline.context import PipelineContext


class TableProcessor:
    """Normalize table layout regions into row/column/cell structures."""

    def run(self, ctx: PipelineContext) -> None:
        regions = ctx.candidates.get("layout_regions", [])
        for region in regions:
            if region.get("kind") != "table_candidate":
                continue
            if region.get("cells"):
                continue
            cells = _extract_cells(region)
            if not cells:
                continue
            region["cells"] = cells
            region["rows"] = len(cells)
            region["cols"] = max((len(row) for row in cells), default=0)
            region["confidence"] = max(float(region.get("confidence", 0.0)), 0.75)
        ctx.candidates["layout_regions"] = regions


def _extract_cells(region: dict[str, Any]) -> list[list[dict[str, Any]]]:
    raw = region.get("raw") if isinstance(region.get("raw"), dict) else region
    explicit = _find_explicit_cells(raw)
    if explicit:
        return explicit
    html_text = _find_table_html(raw) or region.get("text")
    if html_text:
        return _cells_from_html(str(html_text))
    return []


def _find_explicit_cells(value: Any) -> list[list[dict[str, Any]]]:
    for item in _iter_dicts(value):
        for key in ("cells", "cell_list", "table_cells"):
            cells = item.get(key)
            normalized = _normalize_cell_list(cells)
            if normalized:
                return normalized
    return []


def _normalize_cell_list(cells: Any) -> list[list[dict[str, Any]]]:
    if not isinstance(cells, list):
        return []
    rows: dict[int, dict[int, dict[str, Any]]] = {}
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        row = int(cell.get("row", cell.get("row_idx", cell.get("start_row", 0))) or 0)
        col = int(cell.get("col", cell.get("col_idx", cell.get("start_col", 0))) or 0)
        text = cell.get("text", cell.get("content", ""))
        rows.setdefault(row, {})[col] = {
            "row": row,
            "col": col,
            "text": str(text or ""),
            "bbox": cell.get("bbox") or cell.get("cell_bbox"),
        }
    if not rows:
        return []
    max_row = max(rows)
    max_col = max(max(cols) for cols in rows.values())
    return [[rows.get(r, {}).get(c, {}) for c in range(max_col + 1)] for r in range(max_row + 1)]


def _find_table_html(value: Any) -> str | None:
    for item in _iter_dicts(value):
        for key in ("html", "table_html", "pred_html"):
            html_text = item.get(key)
            if html_text and "<table" in str(html_text).lower():
                return str(html_text)
    return None


def _cells_from_html(html_text: str) -> list[list[dict[str, Any]]]:
    try:
        root = html.fromstring(html_text)
    except (ValueError, TypeError):
        return []
    rows: list[list[dict[str, Any]]] = []
    occupied: set[tuple[int, int]] = set()
    for row_index, tr in enumerate(root.xpath(".//tr")):
        row: list[dict[str, Any]] = []
        col_index = 0
        while (row_index, col_index) in occupied:
            row.append({})
            col_index += 1
        for cell_node in tr.xpath("./th|./td"):
            while (row_index, col_index) in occupied:
                row.append({})
                col_index += 1
            rowspan = int(cell_node.get("rowspan", "1") or 1)
            colspan = int(cell_node.get("colspan", "1") or 1)
            text = " ".join(cell_node.text_content().split())
            cell = {"row": row_index, "col": col_index, "text": text}
            row.append(cell)
            for r in range(row_index, row_index + rowspan):
                for c in range(col_index, col_index + colspan):
                    if r == row_index and c == col_index:
                        continue
                    occupied.add((r, c))
            for _ in range(1, colspan):
                row.append({})
                col_index += 1
            col_index += 1
        rows.append(row)
    width = max((len(row) for row in rows), default=0)
    return [row + [{} for _ in range(width - len(row))] for row in rows]


def _iter_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _iter_dicts(nested)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _iter_dicts(item)
