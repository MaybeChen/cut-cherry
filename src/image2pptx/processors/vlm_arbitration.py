from __future__ import annotations

import json
from typing import Any

from image2pptx.core.errors import PipelineStageError, format_stage_failure
from image2pptx.models.vlm import VlmAdapter
from image2pptx.pipeline.context import PipelineContext


class VlmArbitrationProcessor:
    """Use an OpenAI-compatible VLM as semantic arbiter over detected layers.

    The VLM is not allowed to invent coordinates.  It receives compact candidate
    metadata and may only return keep/drop/type/parent/style hints keyed by
    existing ids.
    """

    def __init__(self, adapter: VlmAdapter | None = None) -> None:
        self.adapter = adapter

    def run(self, ctx: PipelineContext) -> None:
        config = getattr(ctx.settings.models, "vlm", {})
        adapter = self.adapter or VlmAdapter(config)
        layers = ctx.candidates.get("layers") if isinstance(ctx.candidates.get("layers"), dict) else {}
        if not layers:
            warnings = [{"reason": "vlm_missing_layers", "message": "Layer decomposition must run before VLM arbitration."}]
            ctx.candidates["vlm_warnings"] = warnings
            raise PipelineStageError(format_stage_failure("vlm", warnings))
        prompt = _build_vlm_prompt(layers)
        result, warnings = adapter.infer_json(prompt, max_tokens=int(config.get("max_tokens", 1200)))
        if warnings:
            ctx.candidates["vlm_warnings"] = warnings
            _write_vlm_report(ctx, status="failed", result=None, warnings=warnings)
            raise PipelineStageError(format_stage_failure("vlm", warnings))
        result = result or {}
        apply_vlm_arbitration(layers, result)
        ctx.candidates["vlm_arbitration"] = result
        _write_vlm_report(ctx, status="succeeded", result=result, warnings=[])


def _build_vlm_prompt(layers: dict[str, Any]) -> list[dict[str, str]]:
    compact = _compact_layers(layers)
    system = (
        "You are a diagram-to-slide reconstruction arbiter. Return strict JSON only. "
        "Do not create new coordinates. Only reference existing ids. Decide semantic_type, "
        "keep/drop, parent_id, and optional style hints for detected candidates."
    )
    user = {
        "task": "arbitrate_layers",
        "schema": {
            "items": [
                {
                    "id": "existing candidate id",
                    "keep": True,
                    "semantic_type": "container|icon_group|icon|text|callout|panel|arrow|shadow|decorative|noise",
                    "parent_id": "optional existing container id",
                    "style": {"fill_color": "#rrggbb", "font_color": "#rrggbb"},
                }
            ]
        },
        "layers": compact,
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]


def _compact_layers(layers: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {"counts": layers.get("counts", {})}
    for key in ("containers", "texts", "assets", "connectors"):
        compact[key] = [
            {
                "id": item.get("id"),
                "kind": item.get("kind") or item.get("layer_kind"),
                "text": item.get("text"),
                "bbox": item.get("bbox"),
                "parent_id": item.get("parent_id"),
                "source": item.get("source"),
                "confidence": item.get("confidence"),
            }
            for item in layers.get(key, [])[:80]
        ]
    return compact


def apply_vlm_arbitration(layers: dict[str, Any], result: dict[str, Any]) -> None:
    decisions = result.get("items") if isinstance(result.get("items"), list) else []
    by_id = {
        str(item.get("id")): item
        for bucket in ("containers", "texts", "assets", "connectors")
        for item in layers.get(bucket, [])
        if item.get("id") is not None
    }
    for decision in decisions:
        candidate_id = str(decision.get("id", ""))
        if not candidate_id or candidate_id not in by_id:
            continue
        item = by_id[candidate_id]
        item["vlm"] = {key: value for key, value in decision.items() if key != "style"}
        if "keep" in decision:
            item["keep"] = bool(decision["keep"])
        if semantic_type := decision.get("semantic_type"):
            item["semantic_type"] = str(semantic_type)
        if parent_id := decision.get("parent_id"):
            item["parent_id"] = str(parent_id)
        style = decision.get("style")
        if isinstance(style, dict):
            item.setdefault("style", {}).update(style)
            for key in ("fill_color", "line_color", "font_color"):
                if key in style:
                    item[key] = style[key]
    for bucket in ("containers", "texts", "assets", "connectors"):
        layers[bucket] = [item for item in layers.get(bucket, []) if item.get("keep", True)]
    layers["counts"] = {key: len(layers.get(key, [])) for key in ("containers", "texts", "assets", "connectors")}


def _write_vlm_report(ctx: PipelineContext, status: str, result: dict[str, Any] | None, warnings: list[dict[str, Any]]) -> None:
    report_path = ctx.job_dir / "vlm_arbitration.json"
    report = {"job_id": ctx.job_id, "status": status, "warnings": warnings, "result": result or {}}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    ctx.artifacts["vlm_arbitration"] = report_path
