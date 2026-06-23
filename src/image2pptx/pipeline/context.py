from __future__ import annotations
from pathlib import Path
from pydantic import BaseModel, Field
from image2pptx.config.settings import Settings

class PipelineContext(BaseModel):
    job_id: str
    input_path: Path
    job_dir: Path
    settings: Settings
    device: str
    artifacts: dict[str, Path] = Field(default_factory=dict)
    candidates: dict[str, list[dict]] = Field(default_factory=dict)
