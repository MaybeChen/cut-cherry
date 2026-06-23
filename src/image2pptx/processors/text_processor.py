from __future__ import annotations

import importlib
import importlib.util
import json
import os
import warnings
from pathlib import Path
from typing import Any, Callable

from image2pptx.pipeline.context import PipelineContext


class TextProcessor:
    def run(self, ctx: PipelineContext) -> None:
        """Run PaddleOCR lazily and normalize output across PaddleOCR 2.x/3.x.

        PaddleOCR 3.x removed the legacy ``use_gpu`` constructor argument and
        uses ``device=\"cpu|gpu\"`` plus ``predict()``. PaddleOCR 2.x uses
        ``use_gpu`` plus ``ocr()``. This adapter tries the 3.x API first and
        falls back to 2.x without allowing constructor API drift to crash the
        whole conversion pipeline.
        """
        blocks: list[dict[str, Any]] = []
        ocr_config = ctx.settings.models.ocr
        if importlib.util.find_spec("paddleocr") is None:
            ctx.candidates["text"] = blocks
            ctx.candidates["text_warnings"] = [{"reason": "paddleocr_not_installed"}]
            _write_ocr_report(ctx, status="skipped", warnings=ctx.candidates["text_warnings"])
            return

        missing_dirs = _missing_model_dirs(_configured_model_dirs(ocr_config))
        if missing_dirs and not bool(ocr_config.get("allow_auto_download", False)):
            ctx.candidates["text"] = blocks
            ctx.candidates["text_warnings"] = [
                {"reason": "local_ocr_model_missing", "missing_dirs": missing_dirs}
            ]
            _write_ocr_report(ctx, status="skipped", warnings=ctx.candidates["text_warnings"])
            return

        _prepare_paddle_runtime_logs()
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*No ccache found.*")
            paddleocr_module = importlib.import_module("paddleocr")
        paddleocr_cls = getattr(paddleocr_module, "PaddleOCR")
        ocr, api_version, ocr_warnings = _create_paddleocr(paddleocr_cls, ocr_config, ctx.device)
        if ocr is None:
            ctx.candidates["text"] = blocks
            ctx.candidates["text_warnings"] = ocr_warnings
            _write_ocr_report(ctx, status="failed", warnings=ocr_warnings)
            return

        try:
            if api_version == "v3" and hasattr(ocr, "predict"):
                result = ocr.predict(str(ctx.artifacts["normalized"]))
            else:
                result = ocr.ocr(
                    str(ctx.artifacts["normalized"]),
                    cls=_use_textline_orientation(ocr_config),
                )
        except (RuntimeError, ValueError, TypeError, OSError) as exc:
            ctx.candidates["text"] = blocks
            ctx.candidates["text_warnings"] = [
                {"reason": "ocr_inference_failed", "message": str(exc)}
            ]
            _write_ocr_report(ctx, status="failed", warnings=ctx.candidates["text_warnings"])
            return

        ctx.candidates["text"] = _normalize_ocr_result(result)
        if ocr_warnings:
            ctx.candidates["text_warnings"] = ocr_warnings
        _write_ocr_report(
            ctx,
            status="succeeded" if ctx.candidates["text"] else "empty",
            warnings=ocr_warnings,
        )


def _prepare_paddle_runtime_logs() -> None:
    # Paddle/PaddleOCR can emit noisy native logs before Python logging is ready.
    # These environment flags must be set before importing paddleocr.
    os.environ.setdefault("GLOG_minloglevel", "2")
    os.environ.setdefault("FLAGS_minloglevel", "2")


def _write_ocr_report(
    ctx: PipelineContext, status: str, warnings: list[dict[str, Any]] | None = None
) -> None:
    report_path = ctx.job_dir / "ocr_results.json"
    report = {
        "job_id": ctx.job_id,
        "status": status,
        "count": len(ctx.candidates.get("text", [])),
        "warnings": warnings or [],
        "items": ctx.candidates.get("text", []),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    ctx.artifacts["ocr_results"] = report_path


def _create_paddleocr(
    paddleocr_cls: Callable[..., Any], ocr_config: dict[str, Any], device: str
) -> tuple[Any | None, str, list[dict[str, str]]]:
    warnings: list[dict[str, str]] = []
    init_plans = [
        ("v3", _build_v3_kwargs(ocr_config, device)),
        ("v2", _build_v2_kwargs(ocr_config, device)),
    ]
    for api_version, kwargs in init_plans:
        try:
            return paddleocr_cls(**kwargs), api_version, warnings
        except ValueError as exc:
            # PaddleOCR raises ValueError("Unknown argument: ...") when users
            # install a different major version. Try the next known API shape.
            warnings.append({"reason": f"paddleocr_{api_version}_init_failed", "message": str(exc)})
        except (RuntimeError, TypeError, OSError) as exc:
            warnings.append({"reason": f"paddleocr_{api_version}_init_failed", "message": str(exc)})
    return None, "unknown", warnings


def _build_v3_kwargs(ocr_config: dict[str, Any], device: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "device": "gpu" if device == "cuda" else "cpu",
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": _use_textline_orientation(ocr_config),
    }
    path_map = {
        "det_model_dir": "text_detection_model_dir",
        "rec_model_dir": "text_recognition_model_dir",
        "cls_model_dir": "textline_orientation_model_dir",
        "det_model_name": "text_detection_model_name",
        "rec_model_name": "text_recognition_model_name",
        "cls_model_name": "textline_orientation_model_name",
    }
    has_explicit_model = False
    for config_key, paddle_key in path_map.items():
        if value := ocr_config.get(config_key):
            kwargs[paddle_key] = str(value)
            has_explicit_model = True

    # PaddleOCR 3.x warns that lang/ocr_version are ignored whenever explicit
    # model names or local model directories are provided. In offline mode we
    # already pin every OCR model path, so omit lang to keep startup clean.
    if not has_explicit_model:
        kwargs["lang"] = ocr_config.get("lang", "ch")
    return kwargs


def _build_v2_kwargs(ocr_config: dict[str, Any], device: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "use_angle_cls": _use_textline_orientation(ocr_config),
        "lang": ocr_config.get("lang", "ch"),
        "use_gpu": device == "cuda",
    }
    path_map = {
        "det_model_dir": "det_model_dir",
        "rec_model_dir": "rec_model_dir",
        "cls_model_dir": "cls_model_dir",
    }
    for config_key, paddle_key in path_map.items():
        if value := ocr_config.get(config_key):
            kwargs[paddle_key] = str(value)
    return kwargs


def _use_textline_orientation(ocr_config: dict[str, Any]) -> bool:
    return bool(ocr_config.get("use_textline_orientation", ocr_config.get("use_angle_cls", True)))


def _configured_model_dirs(ocr_config: dict[str, Any]) -> list[str]:
    return [
        str(ocr_config[key])
        for key in ("det_model_dir", "rec_model_dir", "cls_model_dir")
        if ocr_config.get(key)
    ]


def _missing_model_dirs(model_dirs: list[str]) -> list[str]:
    missing: list[str] = []
    for path in model_dirs:
        model_dir = Path(path)
        if not model_dir.exists() or not any(model_dir.iterdir()):
            missing.append(path)
    return missing


def _normalize_ocr_result(result: Any) -> list[dict[str, Any]]:
    if not result:
        return []
    if _looks_like_v2_result(result):
        return _normalize_v2_result(result)
    return _normalize_v3_result(result)


def _looks_like_v2_result(result: Any) -> bool:
    return isinstance(result, list) and bool(result) and isinstance(result[0], list)


def _normalize_v2_result(result: Any) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for i, line in enumerate(result[0] if result else []):
        pts, (text, conf) = line
        blocks.append(_make_text_block(i, str(text), float(conf), pts))
    return blocks


def _normalize_v3_result(result: Any) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    rows: list[tuple[str, float, Any]] = []
    for page in result if isinstance(result, list) else [result]:
        res = getattr(page, "json", None)
        if callable(res):
            page_data = res().get("res", {})
        elif isinstance(page, dict):
            page_data = page.get("res", page)
        else:
            page_data = getattr(page, "res", {}) or {}
        texts = list(page_data.get("rec_texts", []) or [])
        scores = list(page_data.get("rec_scores", []) or [])
        polys = page_data.get("rec_polys")
        if polys is None:
            polys = page_data.get("dt_polys")
        if polys is None:
            polys = []
        for idx, text in enumerate(texts):
            score = float(scores[idx]) if idx < len(scores) else 0.0
            poly = polys[idx] if idx < len(polys) else []
            rows.append((str(text), score, poly))
    for i, (text, score, poly) in enumerate(rows):
        blocks.append(_make_text_block(i, text, score, poly))
    return blocks


def _make_text_block(i: int, text: str, conf: float, pts: Any) -> dict[str, Any]:
    polygon = (
        [[float(p[0]), float(p[1])] for p in pts]
        if pts is not None and len(pts)
        else []
    )
    xs = [p[0] for p in polygon] or [0.0]
    ys = [p[1] for p in polygon] or [0.0]
    normalized = " ".join(text.split())
    return {
        "id": f"text_{i}",
        "raw_text": text,
        "normalized_text": normalized,
        "text": normalized,
        "bbox": [min(xs), min(ys), max(xs), max(ys)],
        "polygon": polygon,
        "rotation": 0.0,
        "confidence": conf,
        "font_style_candidates": {},
    }
