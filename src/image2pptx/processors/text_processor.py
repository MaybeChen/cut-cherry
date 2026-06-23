from __future__ import annotations

from pathlib import Path
from typing import Any

from image2pptx.pipeline.context import PipelineContext


class TextProcessor:
    def run(self, ctx: PipelineContext) -> None:
        """Run PaddleOCR only when installed and local model files are configured.

        CPU/offline deployments should manually place model weights under ./models
        and set det_model_dir/rec_model_dir/cls_model_dir in YAML. If the local
        model folders are absent and allow_auto_download=false, OCR is skipped
        explicitly instead of triggering a hidden download.
        """
        blocks: list[dict[str, Any]] = []
        ocr_config = ctx.settings.models.ocr
        try:
            from paddleocr import PaddleOCR  # type: ignore
        except ImportError:
            ctx.candidates["text"] = blocks
            ctx.candidates["text_warnings"] = [{"reason": "paddleocr_not_installed"}]
            return

        model_kwargs = _build_model_kwargs(ocr_config)
        missing_dirs = _missing_model_dirs(model_kwargs)
        if missing_dirs and not bool(ocr_config.get("allow_auto_download", False)):
            ctx.candidates["text"] = blocks
            ctx.candidates["text_warnings"] = [
                {"reason": "local_ocr_model_missing", "missing_dirs": missing_dirs}
            ]
            return

        ocr = PaddleOCR(
            use_angle_cls=True,
            lang=ocr_config.get("lang", "ch"),
            use_gpu=ctx.device == "cuda",
            **model_kwargs,
        )
        result = ocr.ocr(str(ctx.artifacts["normalized"]), cls=True)
        for i, line in enumerate(result[0] if result else []):
            pts, (text, conf) = line
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            blocks.append(
                {
                    "id": f"text_{i}",
                    "raw_text": text,
                    "normalized_text": " ".join(str(text).split()),
                    "text": " ".join(str(text).split()),
                    "bbox": [min(xs), min(ys), max(xs), max(ys)],
                    "polygon": pts,
                    "rotation": 0.0,
                    "confidence": float(conf),
                    "font_style_candidates": {},
                }
            )
        ctx.candidates["text"] = blocks


def _build_model_kwargs(ocr_config: dict[str, Any]) -> dict[str, str]:
    key_map = {
        "det_model_dir": "det_model_dir",
        "rec_model_dir": "rec_model_dir",
        "cls_model_dir": "cls_model_dir",
    }
    kwargs: dict[str, str] = {}
    for config_key, paddle_key in key_map.items():
        value = ocr_config.get(config_key)
        if value:
            kwargs[paddle_key] = str(value)
    return kwargs


def _missing_model_dirs(model_kwargs: dict[str, str]) -> list[str]:
    missing: list[str] = []
    for path in model_kwargs.values():
        model_dir = Path(path)
        if not model_dir.exists() or not any(model_dir.iterdir()):
            missing.append(path)
    return missing
