"""Optional SAM3 adapter for visual asset proposals.

The adapter is intentionally lazy/offline-safe.  It can call a configured HTTP
endpoint today, and it leaves a normalized interface for a local SAM3 runtime
when that dependency is installed and wired in a deployment environment.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_PROMPTS = ["icon", "logo", "image", "figure", "diagram symbol"]


class Sam3Adapter:
    def __init__(self, config: dict[str, Any], device: str) -> None:
        self.config = config
        self.device = device

    def infer(self, image_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not bool(self.config.get("enabled", True)):
            return [], [{"reason": "sam3_disabled"}]
        endpoint = self.config.get("endpoint")
        if endpoint:
            return self._infer_endpoint(str(endpoint), image_path)
        model_path = self.config.get("model_path")
        if model_path and Path(str(model_path)).exists():
            return self._infer_local(image_path)
        return [], [
            {
                "reason": "sam3_not_configured",
                "message": "Set models.sam3.endpoint or models.sam3.model_path to enable SAM3 visual proposals.",
            }
        ]

    def _infer_endpoint(
        self, endpoint: str, image_path: Path
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        payload = {
            "image_path": str(image_path),
            "prompts": self.config.get("prompts", DEFAULT_PROMPTS),
            "device": self.device,
        }
        request = Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=float(self.config.get("timeout", 30))) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            return [], [{"reason": "sam3_endpoint_failed", "message": str(exc)}]
        return normalize_sam3_result(raw), []

    def _infer_local(self, image_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if importlib.util.find_spec("sam3") is None:
            return [], [
                {
                    "reason": "sam3_runtime_not_installed",
                    "message": "Install the SAM3 runtime or configure models.sam3.endpoint.",
                }
            ]
        return [], [
            {
                "reason": "sam3_local_runtime_not_wired",
                "message": "Local SAM3 package was found, but this service expects an endpoint adapter until the runtime API is stabilized.",
                "image_path": str(image_path),
            }
        ]


def normalize_sam3_result(raw: Any) -> list[dict[str, Any]]:
    records = raw.get("regions", raw.get("items", raw)) if isinstance(raw, dict) else raw
    regions = []
    for item in _iter_dicts(records):
        bbox = _extract_bbox(item)
        if bbox is None:
            continue
        label = _extract_label(item)
        regions.append(
            {
                "id": f"sam3_{len(regions)}",
                "kind": _normalize_kind(label),
                "bbox": bbox,
                "confidence": float(item.get("score", item.get("confidence", 0.7)) or 0.7),
                "source": "sam3",
                "raw": item,
            }
        )
    return regions


def _iter_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _iter_dicts(nested)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _iter_dicts(item)


def _extract_bbox(item: dict[str, Any]) -> list[float] | None:
    for key in ("bbox", "box", "mask_bbox"):
        value = item.get(key)
        if isinstance(value, list | tuple) and len(value) >= 4:
            x1, y1, x2, y2 = [float(v) for v in value[:4]]
            return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
    return None


def _extract_label(item: dict[str, Any]) -> str:
    for key in ("label", "concept", "category", "type", "prompt"):
        if item.get(key):
            return str(item[key])
    return "image"


def _normalize_kind(label: str) -> str:
    label = label.lower()
    if "logo" in label:
        return "logo_candidate"
    if "icon" in label or "symbol" in label:
        return "icon_candidate"
    return "image_candidate"
