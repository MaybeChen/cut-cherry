from __future__ import annotations
from pydantic import BaseModel, Field


class QualityReport(BaseModel):
    visual_score: float = 0.0
    text_score: float = 0.0
    edge_score: float = 0.0
    patch_area_ratio: float = 0.0
    issues: list[str] = Field(default_factory=list)
