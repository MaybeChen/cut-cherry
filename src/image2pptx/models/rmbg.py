"""Optional RMBG adapter for alpha-mask generation.

The adapter is lazy/offline-safe.  If an ONNX model and onnxruntime are
available it attempts a generic image-to-alpha inference path; callers should
raise a stage error when the runtime is unavailable.
"""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


class RmbgAdapter:
    def __init__(self, config: dict[str, Any], device: str = "cpu") -> None:
        self.config = config
        self.device = device
        self._session: Any | None = None

    def available(self) -> bool:
        model_path = self.config.get("model_path")
        return (
            bool(self.config.get("enabled", True))
            and bool(model_path)
            and Path(str(model_path)).exists()
            and importlib.util.find_spec("onnxruntime") is not None
        )

    def infer_alpha(self, image: Image.Image) -> tuple[Image.Image | None, list[dict[str, str]]]:
        if not bool(self.config.get("enabled", True)):
            return None, [{"reason": "rmbg_disabled"}]
        if not self.available():
            return None, [{"reason": "rmbg_not_available"}]
        try:
            session = self._get_session()
            alpha = _run_onnx_alpha(session, image, int(self.config.get("input_size", 1024)))
        except Exception as exc:  # pragma: no cover - defensive optional runtime path
            return None, [{"reason": "rmbg_inference_failed", "message": str(exc)}]
        return alpha, []

    def _get_session(self) -> Any:
        if self._session is None:
            ort = importlib.import_module("onnxruntime")
            providers = ["CPUExecutionProvider"]
            if self.device == "cuda" and "CUDAExecutionProvider" in ort.get_available_providers():
                providers.insert(0, "CUDAExecutionProvider")
            self._session = ort.InferenceSession(
                str(self.config["model_path"]), providers=providers
            )
        return self._session


class OptionalModelAdapter(RmbgAdapter):
    """Backward-compatible alias for old imports."""


def _run_onnx_alpha(session: Any, image: Image.Image, input_size: int) -> Image.Image:
    original_size = image.size
    resized = image.convert("RGB").resize((input_size, input_size), Image.Resampling.BILINEAR)
    arr = np.asarray(resized).astype("float32") / 255.0
    arr = np.transpose(arr, (2, 0, 1))[None, ...]
    input_name = session.get_inputs()[0].name
    output = session.run(None, {input_name: arr})[0]
    alpha_arr = np.asarray(output).squeeze()
    alpha_arr = _normalize_alpha(alpha_arr)
    alpha = Image.fromarray(alpha_arr, mode="L").resize(original_size, Image.Resampling.BILINEAR)
    return alpha


def _normalize_alpha(alpha: np.ndarray) -> np.ndarray:
    alpha = alpha.astype("float32")
    if alpha.max() > 1.0:
        alpha = alpha / 255.0
    alpha = np.clip(alpha, 0.0, 1.0)
    return (alpha * 255).astype("uint8")
