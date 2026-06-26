from __future__ import annotations
from enum import StrEnum
from pydantic import BaseModel


class RelationType(StrEnum):
    CONTAINS = "contains"
    BELONGS_TO = "belongs_to"
    ALIGN_LEFT = "align_left"
    ALIGN_CENTER = "align_center"
    SAME_STYLE = "same_style"
    CONNECTS_TO = "connects_to"
    CAPTION_OF = "caption_of"
    LEGEND_OF = "legend_of"
    OVERLAPS = "overlaps"
    REPEATED_WITH = "repeated_with"


class ElementRelation(BaseModel):
    source_id: str
    target_id: str
    type: RelationType
    confidence: float = 1.0
