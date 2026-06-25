"""Optional PaddleOCR layout model adapters.

Heavy PaddleOCR/PaddleX modules are discovered and imported lazily inside model
methods so importing image2pptx remains lightweight and offline-safe.
"""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
from typing import Any


class LayoutModelAdapter:
    def __init__(self, config: dict[str, Any], device: str) -> None:
        self.config = config
        self.device = device
        self.engine = str(config.get("engine", "rules")).lower()
        self._pipeline: Any | None = None

    def available(self) -> tuple[bool, list[dict[str, Any]]]:
        warnings: list[dict[str, Any]] = []
        if self.engine in {"rules", "rule", "none"}:
            return False, [{"reason": "layout_engine_rules"}]
        if self.engine in {"pp_structure", "ppstructure", "pp_structure_v3", "ppstructurev3"}:
            if importlib.util.find_spec("paddleocr") is None:
                return False, [{"reason": "paddleocr_not_installed"}]
            return self._check_download_policy(warnings)
        if self.engine in {"paddleocr_vl", "paddleocr-vl", "paddleocrvl"}:
            if (
                importlib.util.find_spec("paddlex") is None
                and importlib.util.find_spec("paddleocr") is None
            ):
                return False, [{"reason": "paddleocr_vl_runtime_not_installed"}]
            return self._check_download_policy(warnings)
        return False, [{"reason": "unsupported_layout_engine", "engine": self.engine}]

    def infer(self, image_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        available, warnings = self.available()
        if not available:
            return [], warnings
        pipeline = self._get_pipeline()
        raw = _predict(pipeline, image_path, self.config)
        regions = normalize_layout_result(raw)
        return regions, warnings

    def _check_download_policy(
        self, warnings: list[dict[str, Any]]
    ) -> tuple[bool, list[dict[str, Any]]]:
        if bool(self.config.get("allow_auto_download", False)):
            return True, warnings
        configured_paths = [
            self.config.get("paddlex_config"),
            self.config.get("model_dir"),
            self.config.get("layout_model_dir"),
        ]
        if any(path and Path(str(path)).exists() for path in configured_paths):
            return True, warnings
        return False, [
            {
                "reason": "local_layout_model_missing",
                "engine": self.engine,
                "message": "Set models.layout.allow_auto_download=true or configure an existing paddlex_config/model_dir.",
            }
        ]

    def _get_pipeline(self) -> Any:
        if self._pipeline is None:
            self._pipeline = _create_pipeline(self.engine, self.config, self.device)
        return self._pipeline


def _create_pipeline(engine: str, config: dict[str, Any], device: str) -> Any:
    if engine in {"pp_structure", "ppstructure", "pp_structure_v3", "ppstructurev3"}:
        paddleocr = importlib.import_module("paddleocr")
        cls = getattr(paddleocr, "PPStructureV3", None) or getattr(paddleocr, "PPStructure", None)
        if cls is None:
            raise RuntimeError("paddleocr does not expose PPStructureV3 or PPStructure")
        kwargs = _build_common_kwargs(config, device)
        return cls(**kwargs)

    if engine in {"paddleocr_vl", "paddleocr-vl", "paddleocrvl"}:
        if importlib.util.find_spec("paddlex") is not None:
            paddlex = importlib.import_module("paddlex")
            create_pipeline = getattr(paddlex, "create_pipeline")
            pipeline = (
                str(config["paddlex_config"])
                if config.get("paddlex_config")
                else config.get("pipeline_name", "PaddleOCR-VL")
            )
            return create_pipeline(pipeline=pipeline)
        paddleocr = importlib.import_module("paddleocr")
        cls = getattr(paddleocr, "PaddleOCRVL", None)
        if cls is None:
            raise RuntimeError("PaddleOCR-VL runtime is not available")
        kwargs = _build_common_kwargs(config, device)
        return cls(**kwargs)

    raise RuntimeError(f"unsupported layout engine: {engine}")


def _build_common_kwargs(config: dict[str, Any], device: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if config.get("paddlex_config"):
        kwargs["paddlex_config"] = str(config["paddlex_config"])
    if config.get("model_dir"):
        kwargs["model_dir"] = str(config["model_dir"])
    if config.get("layout_model_dir"):
        kwargs["layout_model_dir"] = str(config["layout_model_dir"])
    kwargs["device"] = "gpu" if device == "cuda" else "cpu"
    return kwargs


def _predict(pipeline: Any, image_path: Path, config: dict[str, Any]) -> Any:
    predict_kwargs = {
        "use_table_recognition": bool(config.get("use_table_recognition", True)),
        "use_formula_recognition": bool(config.get("use_formula_recognition", True)),
        "use_chart_recognition": bool(config.get("use_chart_recognition", True)),
        "use_region_detection": bool(config.get("use_region_detection", True)),
    }
    if hasattr(pipeline, "predict"):
        try:
            return pipeline.predict(input=str(image_path), **predict_kwargs)
        except TypeError:
            return pipeline.predict(str(image_path))
    if callable(pipeline):
        return pipeline(str(image_path))
    raise RuntimeError("layout pipeline does not provide predict() or __call__")


def normalize_layout_result(raw: Any) -> list[dict[str, Any]]:
    regions = []
    for index, item in enumerate(_iter_dicts(raw)):
        bbox = _extract_bbox(item)
        if bbox is None:
            continue
        label = _extract_label(item)
        regions.append(
            {
                "id": f"layout_model_{len(regions)}",
                "kind": _normalize_kind(label),
                "bbox": bbox,
                "confidence": float(item.get("score", item.get("confidence", 0.7)) or 0.7),
                "text": item.get("text") or item.get("content") or item.get("html"),
                "source": "layout_model",
                "raw": item,
            }
        )
    return regions


def _iter_dicts(value: Any):
    if hasattr(value, "json") and callable(value.json):
        value = value.json()
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _iter_dicts(nested)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _iter_dicts(item)


def _extract_bbox(item: dict[str, Any]) -> list[float] | None:
    for key in ("bbox", "block_bbox", "coordinate", "box"):
        value = item.get(key)
        bbox = _coerce_bbox(value)
        if bbox is not None:
            return bbox
    return None


def _coerce_bbox(value: Any) -> list[float] | None:
    if not isinstance(value, list | tuple) or len(value) < 4:
        return None
    if all(isinstance(v, int | float) for v in value[:4]):
        x1, y1, x2, y2 = [float(v) for v in value[:4]]
        return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
    if all(isinstance(point, list | tuple) and len(point) >= 2 for point in value):
        xs = [float(point[0]) for point in value]
        ys = [float(point[1]) for point in value]
        return [min(xs), min(ys), max(xs), max(ys)]
    return None


def _extract_label(item: dict[str, Any]) -> str:
    for key in ("label", "type", "block_label", "layout_label", "category"):
        if item.get(key):
            return str(item[key])
    return "text"


def _normalize_kind(label: str) -> str:
    label = label.lower()
    if "table" in label:
        return "table_candidate"
    if "image" in label or "figure" in label or "pic" in label:
        return "image_candidate"
    if "title" in label:
        return "title"
    if "formula" in label or "equation" in label:
        return "formula"
    if "chart" in label:
        return "chart"
    return "paragraph"
