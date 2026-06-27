from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ElementGroup(StrEnum):
    BACKGROUND = "background"
    CONTAINER = "container"
    TEXT = "text"
    ASSET = "asset"
    CONNECTOR = "connector"
    TABLE = "table"
    FORMULA = "formula"
    CHART = "chart"
    RESIDUAL = "residual"


class CandidateElement(BaseModel):
    """Unified element candidate passed between layered pipeline stages."""

    id: str
    group: ElementGroup
    bbox: list[float] = Field(default_factory=list)
    score: float = 1.0
    source: str = "unknown"
    layer: str | None = None
    kind: str | None = None
    text: str | None = None
    style: dict[str, Any] = Field(default_factory=dict)
    parent_id: str | None = None
    source_container_id: str | None = None
    target_container_id: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


def build_element_groups(layers: dict[str, Any], candidates: dict[str, Any]) -> dict[str, Any]:
    """Build the Edit-Banana-style group-first contract from layered buckets."""

    groups: dict[str, Any] = {group.value: [] for group in ElementGroup}
    groups[ElementGroup.BACKGROUND.value].append(
        CandidateElement(
            id="background",
            group=ElementGroup.BACKGROUND,
            bbox=[],
            score=1.0,
            source="layer_decomposition",
            layer="background",
            kind=str((layers.get("background") or {}).get("strategy", "background")),
            raw=layers.get("background") or {},
        ).model_dump(mode="json")
    )
    for layer_name, group in (
        ("containers", ElementGroup.CONTAINER),
        ("texts", ElementGroup.TEXT),
        ("assets", ElementGroup.ASSET),
        ("connectors", ElementGroup.CONNECTOR),
    ):
        for index, item in enumerate(layers.get(layer_name, []) or []):
            groups[group.value].append(_candidate_from_layer_item(item, group, layer_name, index))

    for table in _regions_of_kind(candidates.get("layout_regions", []), "table_candidate"):
        groups[ElementGroup.TABLE.value].append(
            _candidate_from_raw(
                table, ElementGroup.TABLE, "table", table.get("source", "layout_parser")
            )
        )
    for formula in candidates.get("formulas", []) or []:
        groups[ElementGroup.FORMULA.value].append(
            _candidate_from_raw(formula, ElementGroup.FORMULA, "formula", "formula_processor")
        )
    for chart in candidates.get("charts", []) or []:
        groups[ElementGroup.CHART.value].append(
            _candidate_from_raw(chart, ElementGroup.CHART, "chart", "chart_processor")
        )
    groups["counts"] = {key: len(value) for key, value in groups.items() if isinstance(value, list)}
    return groups


def grouped_candidates(element_groups: dict[str, Any], group: ElementGroup) -> list[dict[str, Any]]:
    return [dict(item.get("raw") or item) for item in element_groups.get(group.value, []) or []]


def _candidate_from_layer_item(
    item: dict[str, Any], group: ElementGroup, layer_name: str, index: int
) -> dict[str, Any]:
    bbox = (
        [float(value) for value in item.get("bbox", [])]
        if len(item.get("bbox", [])) == 4
        else []
    )
    candidate = CandidateElement(
        id=str(item.get("id") or f"{group.value}_{index}"),
        group=group,
        bbox=bbox,
        score=float(item.get("confidence", item.get("score", 0.5))),
        source=str(item.get("source", "layer_decomposition")),
        layer=layer_name,
        kind=item.get("kind") or item.get("semantic_type") or item.get("shape_type"),
        text=item.get("text"),
        style=dict(item.get("style") or {}),
        parent_id=item.get("parent_id"),
        source_container_id=item.get("source_container_id"),
        target_container_id=item.get("target_container_id"),
        provenance={"source_id": item.get("source_id"), "layer": layer_name},
        raw=item,
    )
    return candidate.model_dump(mode="json")


def _candidate_from_raw(
    item: dict[str, Any], group: ElementGroup, layer_name: str, source: str
) -> dict[str, Any]:
    bbox = (
        [float(value) for value in item.get("bbox", [])]
        if len(item.get("bbox", [])) == 4
        else []
    )
    candidate = CandidateElement(
        id=str(item.get("id") or f"{group.value}_{len(str(item))}"),
        group=group,
        bbox=bbox,
        score=float(item.get("confidence", item.get("score", 0.5))),
        source=source,
        layer=layer_name,
        kind=item.get("kind") or item.get("semantic_type") or item.get("shape_type"),
        text=item.get("text"),
        style=dict(item.get("style") or {}),
        parent_id=item.get("parent_id"),
        provenance={"layer": layer_name},
        raw=item,
    )
    return candidate.model_dump(mode="json")


def _regions_of_kind(regions: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [region for region in regions if region.get("kind") == kind]
