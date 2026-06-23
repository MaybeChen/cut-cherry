from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ElementType(StrEnum):
    BACKGROUND = "background"; SHAPE = "shape"; TEXT = "text"; RICH_TEXT = "rich_text"; FORMULA = "formula"; IMAGE = "image"; ICON = "icon"; LOGO = "logo"; CHART = "chart"; TABLE = "table"; CONNECTOR = "connector"; GROUP = "group"; DECORATION = "decoration"; UNKNOWN_PATCH = "unknown_patch"


class EditableStrategy(StrEnum):
    NATIVE_SHAPE = "native_shape"; NATIVE_TEXT = "native_text"; NATIVE_TABLE = "native_table"; NATIVE_CHART = "native_chart"; NATIVE_CONNECTOR = "native_connector"; OFFICE_MATH = "office_math"; SVG_ASSET = "svg_asset"; TRANSPARENT_PNG = "transparent_png"; RASTER_IMAGE = "raster_image"; RESIDUAL_PATCH = "residual_patch"


class Rect(BaseModel):
    x: float; y: float; width: float; height: float
    @property
    def x2(self) -> float: return self.x + self.width
    @property
    def y2(self) -> float: return self.y + self.height
    def area(self) -> float: return max(0.0, self.width) * max(0.0, self.height)


class Provenance(BaseModel):
    source: str
    raw: dict[str, Any] = Field(default_factory=dict)


class ElementStyle(BaseModel):
    fill_color: str | None = None
    line_color: str | None = None
    line_width: float = 1.0
    font_family: str = "Arial"
    font_size: float | None = None
    font_color: str = "#000000"
    bold: bool = False
    italic: bool = False
    align: str = "left"
    shape_type: str | None = None


class SlideElement(BaseModel):
    id: str
    type: ElementType
    bbox: Rect
    rotation: float = 0.0
    z_index: int = 0
    parent_id: str | None = None
    children_ids: list[str] = Field(default_factory=list)
    style: ElementStyle = Field(default_factory=ElementStyle)
    confidence: float = 1.0
    provenance: Provenance = Field(default_factory=lambda: Provenance(source="unknown"))
    editable_strategy: EditableStrategy
    text: str | None = None
    asset_path: Path | None = None


class ConnectorElement(SlideElement):
    source_id: str | None = None
    target_id: str | None = None
    route_points: list[tuple[float, float]] = Field(default_factory=list)
    begin_arrow: str | None = None
    end_arrow: str | None = None
