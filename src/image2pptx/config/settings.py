from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeSettings(BaseModel):
    device: str = "auto"
    max_workers: int = 1
    enable_gpu_memory_cleanup: bool = True


class PipelineSettings(BaseModel):
    enable_layout: bool = True
    enable_text: bool = True
    enable_formula: bool = True
    enable_table: bool = True
    enable_chart: bool = True
    enable_geometry: bool = True
    enable_sam3: bool = True
    enable_rmbg: bool = True
    enable_vlm: bool = False
    enable_refinement: bool = True
    enable_residual_patches: bool = True


class ModelSettings(BaseModel):
    ocr: dict[str, Any] = Field(default_factory=lambda: {"engine": "paddleocr", "lang": "ch"})
    layout: dict[str, Any] = Field(default_factory=lambda: {"engine": "paddleocr_vl"})
    sam3: dict[str, Any] = Field(default_factory=lambda: {"enabled": True})
    rmbg: dict[str, Any] = Field(default_factory=lambda: {"enabled": True})
    vlm: dict[str, Any] = Field(default_factory=lambda: {"enabled": False})
    formula_ocr: dict[str, Any] = Field(
        default_factory=lambda: {"enabled": False, "engine": "pix2text"}
    )


class RenderSettings(BaseModel):
    slide_size_mode: str = "auto"
    default_widescreen_ratio: str = "16:9"
    use_native_charts: bool = True
    use_native_tables: bool = True
    use_native_connectors: bool = True


class QualitySettings(BaseModel):
    enabled: bool = True
    min_visual_score: float = 0.90
    min_text_score: float = 0.95
    max_patch_area_ratio: float = 0.10
    save_diff_image: bool = True


class OutputSettings(BaseModel):
    root_dir: str = "outputs"
    keep_intermediate: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IMAGE2PPTX_", env_nested_delimiter="__")
    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)
    models: ModelSettings = Field(default_factory=ModelSettings)
    render: RenderSettings = Field(default_factory=RenderSettings)
    quality: QualitySettings = Field(default_factory=QualitySettings)
    output: OutputSettings = Field(default_factory=OutputSettings)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_settings(config_path: Path | None = None, device: str | None = None) -> Settings:
    default_path = Path("config/default.yaml")
    data: dict[str, Any] = {}
    if default_path.exists():
        data = yaml.safe_load(default_path.read_text(encoding="utf-8")) or {}
    if config_path:
        data = _deep_merge(data, yaml.safe_load(config_path.read_text(encoding="utf-8")) or {})
    if device:
        data = _deep_merge(data, {"runtime": {"device": device}})
    settings = Settings.model_validate(data)
    # 环境变量覆盖常见开关；复杂嵌套仍由 pydantic-settings 支持实例化。
    if env_device := os.getenv("IMAGE2PPTX_RUNTIME__DEVICE"):
        settings.runtime.device = env_device
    return settings
