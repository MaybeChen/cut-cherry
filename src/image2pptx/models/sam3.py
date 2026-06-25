"""Optional SAM3 adapter for visual asset proposals.

The adapter is intentionally lazy/offline-safe. It supports the Edit-Banana
SAM3 HTTP service schema and, when the SAM3 runtime is installed, can run a
local image model without importing torch/sam3 at module import time.
"""

from __future__ import annotations

import base64
import importlib
import importlib.util
import io
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image


DEFAULT_PROMPTS = ["icon", "logo", "image", "figure", "diagram symbol"]


class Sam3Adapter:
    def __init__(self, config: dict[str, Any], device: str) -> None:
        self.config = config
        self.device = device
        self._local_runtime: _LocalSam3Runtime | None = None

    def infer(self, image_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not bool(self.config.get("enabled", True)):
            return [], [{"reason": "sam3_disabled"}]
        endpoint = self.config.get("endpoint")
        if endpoint:
            return self._infer_endpoint(str(endpoint), image_path)
        model_path = self.config.get("model_path") or self.config.get("checkpoint_path")
        if model_path and Path(str(model_path)).exists():
            return self._infer_local(image_path)
        return [], [
            {
                "reason": "sam3_not_configured",
                "message": (
                    "Set models.sam3.endpoint or models.sam3.model_path/checkpoint_path "
                    "to enable SAM3 visual proposals."
                ),
            }
        ]

    def _infer_endpoint(
        self, endpoint: str, image_path: Path
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        payload = {
            "image_path": str(image_path),
            "prompts": self.config.get("prompts", DEFAULT_PROMPTS),
            "return_masks": bool(self.config.get("return_masks", False)),
            "mask_format": self.config.get("mask_format", "rle"),
        }
        for key in ("score_threshold", "epsilon_factor", "min_area"):
            if self.config.get(key) is not None:
                payload[key] = self.config[key]
        if self.config.get("send_device", False):
            payload["device"] = self.device
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
        try:
            if self._local_runtime is None:
                self._local_runtime = _LocalSam3Runtime(self.config, self.device)
            raw = self._local_runtime.predict(image_path)
        except Exception as exc:  # pragma: no cover - defensive integration path
            return [], [{"reason": "sam3_local_runtime_failed", "message": str(exc)}]
        return normalize_sam3_result(raw), []


class _LocalSam3Runtime:
    def __init__(self, config: dict[str, Any], device: str) -> None:
        torch = importlib.import_module("torch")
        builder = importlib.import_module("sam3.model_builder")
        processor_mod = importlib.import_module("sam3.model.sam3_image_processor")
        self.torch = torch
        self.config = config
        self.device = _resolve_device(torch, config.get("device") or device)
        checkpoint_path = config.get("model_path") or config.get("checkpoint_path")
        bpe_path = config.get("bpe_path")
        with _redirect_cuda_allocations_when_cpu_only(torch, self.device):
            self.model = builder.build_sam3_image_model(
                bpe_path=bpe_path,
                checkpoint_path=checkpoint_path,
                load_from_HF=bool(config.get("load_from_hf", False)),
                device=self.device,
            )
        _install_cpu_dtype_compatibility_hooks(torch, self.model, self.device)
        self.processor = processor_mod.Sam3Processor(self.model, device=self.device)

    def predict(self, image_path: Path) -> dict[str, Any]:
        image = Image.open(image_path).convert("RGB")
        width, height = image.size
        results: list[dict[str, Any]] = []
        score_threshold = float(self.config.get("score_threshold", 0.5))
        min_area = int(self.config.get("min_area", 100))
        prompts = self.config.get("prompts", DEFAULT_PROMPTS)
        with _redirect_cuda_allocations_when_cpu_only(self.torch, self.device):
            state = self.processor.set_image(image)
            for prompt in prompts:
                self.processor.reset_all_prompts(state)
                result_state = self.processor.set_text_prompt(prompt=prompt, state=state)
                results.extend(
                    _detections_from_state(
                        result_state,
                        prompt=str(prompt),
                        score_threshold=score_threshold,
                        min_area=min_area,
                        return_masks=bool(self.config.get("return_masks", False)),
                    )
                )
        return {"image_size": {"width": width, "height": height}, "results": results}


def normalize_sam3_result(raw: Any) -> list[dict[str, Any]]:
    records = _top_level_records(raw)
    regions = []
    for item in _iter_dicts(records):
        bbox = _extract_bbox(item)
        if bbox is None:
            continue
        label = _extract_label(item)
        region = {
            "id": f"sam3_{len(regions)}",
            "kind": _normalize_kind(label),
            "bbox": bbox,
            "confidence": float(item.get("score", item.get("confidence", 0.7)) or 0.7),
            "source": "sam3",
            "raw": item,
        }
        polygon = item.get("polygon") or item.get("contour")
        if isinstance(polygon, list) and polygon:
            region["polygon"] = polygon
        mask = _decode_mask(item.get("mask"))
        if mask is not None:
            region["mask"] = mask
        regions.append(region)
    return regions


def _top_level_records(raw: Any) -> Any:
    if not isinstance(raw, dict):
        return raw
    for key in ("results", "regions", "items", "detections"):
        if key in raw:
            return raw[key]
    return raw


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
    polygon = item.get("polygon") or item.get("contour")
    if isinstance(polygon, list) and polygon:
        points = np.asarray(polygon, dtype=float).reshape(-1, 2)
        x1, y1 = points.min(axis=0)
        x2, y2 = points.max(axis=0)
        return [float(x1), float(y1), float(x2), float(y2)]
    return None


def _extract_label(item: dict[str, Any]) -> str:
    for key in ("label", "concept", "category", "type", "prompt"):
        if item.get(key):
            return str(item[key])
    return "image"


def _normalize_kind(label: str) -> str:
    label = label.lower().replace("_", " ")
    if "logo" in label:
        return "logo_candidate"
    if "icon" in label or "symbol" in label:
        return "icon_candidate"
    return "image_candidate"


def _resolve_device(torch: Any, requested: str | None) -> str:
    device = requested or "auto"
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if str(device).startswith("cuda") and not torch.cuda.is_available():
        return "cpu"
    return str(device)


@contextmanager
def _redirect_cuda_allocations_when_cpu_only(torch: Any, device: str):
    if device != "cpu" or torch.cuda.is_available():
        yield
        return
    factory_names = ("arange", "empty", "full", "linspace", "ones", "rand", "randn", "tensor", "zeros")
    originals = {name: getattr(torch, name) for name in factory_names}
    original_pin_memory = torch.Tensor.pin_memory

    def make_cpu_fallback(original_func):
        def cpu_fallback(*args, **kwargs):
            requested_device = kwargs.get("device")
            if requested_device is not None and str(requested_device).startswith("cuda"):
                kwargs["device"] = "cpu"
            return original_func(*args, **kwargs)

        return cpu_fallback

    for name, original in originals.items():
        setattr(torch, name, make_cpu_fallback(original))
    torch.Tensor.pin_memory = lambda tensor, *args, **kwargs: tensor
    try:
        yield
    finally:
        for name, original in originals.items():
            setattr(torch, name, original)
        torch.Tensor.pin_memory = original_pin_memory


def _install_cpu_dtype_compatibility_hooks(torch: Any, model: Any, device: str) -> None:
    if device != "cpu":
        return

    def match_linear_input_dtype(module, inputs):
        if not inputs:
            return inputs
        first_arg = inputs[0]
        if (
            isinstance(first_arg, torch.Tensor)
            and first_arg.is_floating_point()
            and first_arg.dtype != module.weight.dtype
        ):
            return (first_arg.to(dtype=module.weight.dtype),) + inputs[1:]
        return inputs

    for module in model.modules():
        if isinstance(module, torch.nn.Linear):
            module.register_forward_pre_hook(match_linear_input_dtype)


def _detections_from_state(
    result_state: dict[str, Any], prompt: str, score_threshold: float, min_area: int, return_masks: bool
) -> list[dict[str, Any]]:
    detections: list[dict[str, Any]] = []
    masks = result_state.get("masks", [])
    boxes = result_state.get("boxes", [])
    scores = result_state.get("scores", [])
    if masks is None or len(masks) == 0:
        return detections
    for index in range(len(masks)):
        score = _to_float(scores[index] if len(scores) > index else 0.7)
        if score < score_threshold:
            continue
        bbox = [int(v) for v in _to_numpy(boxes[index]).reshape(-1)[:4].tolist()]
        area = max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1])
        if area < min_area:
            continue
        item: dict[str, Any] = {"prompt": prompt, "score": score, "bbox": bbox, "area": area}
        if return_masks:
            mask = (_to_numpy(masks[index]).squeeze() > 0.5).astype(np.uint8) * 255
            item["mask"] = {"data": _encode_mask_rle(mask), "format": "rle", "shape": list(mask.shape)}
        detections.append(item)
    return detections


def _to_numpy(value: Any) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def _to_float(value: Any) -> float:
    return float(value.item() if hasattr(value, "item") else value)


def _encode_mask_rle(mask: np.ndarray) -> str:
    flat = mask.reshape(-1).astype(np.uint8)
    if flat.size == 0:
        return ""
    runs: list[int] = []
    last_val = flat[0]
    length = 1
    for val in flat[1:]:
        if val == last_val:
            length += 1
        else:
            runs.append(length)
            length = 1
            last_val = val
    runs.append(length)
    return ",".join(str(x) for x in runs)


def _decode_mask(mask: Any) -> dict[str, Any] | None:
    if not isinstance(mask, dict):
        return None
    fmt = mask.get("format")
    data = mask.get("data")
    shape = mask.get("shape")
    if fmt == "rle" and isinstance(data, str) and isinstance(shape, list):
        return {"format": "rle", "data": data, "shape": shape}
    if fmt == "png" and isinstance(data, str):
        try:
            Image.open(io.BytesIO(base64.b64decode(data))).verify()
        except Exception:
            return None
        return {"format": "png", "data": data, "shape": shape}
    return None
