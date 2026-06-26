from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image
from pydantic import BaseModel, Field

from image2pptx.ir.elements import Rect, SlideElement
from image2pptx.ir.relations import ElementRelation, RelationType


class SlideIR(BaseModel):
    width: int
    height: int
    elements: list[SlideElement] = Field(default_factory=list)
    relations: list[ElementRelation] = Field(default_factory=list)

    def validate_scene(self) -> None:
        ids = {e.id for e in self.elements}
        if len(ids) != len(self.elements):
            raise ValueError("SlideIR contains duplicate element ids")
        for e in self.elements:
            if e.parent_id and e.parent_id not in ids:
                raise ValueError(f"missing parent_id={e.parent_id}")

    def sort_by_z_index(self) -> list[SlideElement]:
        return sorted(self.elements, key=lambda e: e.z_index)

    def find_overlaps(self, min_iou: float = 0.01) -> list[ElementRelation]:
        overlaps: list[ElementRelation] = []
        for i, left in enumerate(self.elements):
            for right in self.elements[i + 1 :]:
                if _iou(left.bbox, right.bbox) >= min_iou:
                    overlaps.append(
                        ElementRelation(
                            source_id=left.id, target_id=right.id, type=RelationType.OVERLAPS
                        )
                    )
        return overlaps

    def export_json(self, path: Path) -> None:
        payload = _json_safe(self.model_dump(mode="python"))
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load_json(cls, path: Path) -> "SlideIR":
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _iou(a: Rect, b: Rect) -> float:
    ix1, iy1, ix2, iy2 = max(a.x, b.x), max(a.y, b.y), min(a.x2, b.x2), min(a.y2, b.y2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = a.area() + b.area() - inter
    return inter / union if union else 0.0


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(nested) for key, nested in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_safe(nested) for nested in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Image.Image):
        return f"<PIL.Image mode={value.mode} size={value.size}>"
    if hasattr(value, "tolist") and callable(value.tolist):
        return _json_safe(value.tolist())
    try:
        json.dumps(value)
    except TypeError:
        return repr(value)
    return value
