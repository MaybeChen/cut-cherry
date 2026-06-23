from __future__ import annotations
import uuid
from pathlib import Path
from image2pptx.config.device import resolve_device
from image2pptx.config.settings import Settings
from image2pptx.pipeline.context import PipelineContext
from image2pptx.processors.preprocess import PreprocessProcessor
from image2pptx.processors.text_processor import TextProcessor
from image2pptx.processors.geometry_processor import GeometryProcessor
from image2pptx.processors.arrow_processor import ArrowProcessor
from image2pptx.processors.candidate_fusion import CandidateFusionProcessor
from image2pptx.renderers.pptx_renderer import PptxRenderer

class PipelineResult:
    def __init__(self, job_id: str, job_dir: Path, pptx_path: Path, ir_path: Path) -> None:
        self.job_id=job_id; self.job_dir=job_dir; self.pptx_path=pptx_path; self.ir_path=ir_path

class ImageToPptxPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings=settings
    def run(self, input_path: Path) -> PipelineResult:
        device=resolve_device(self.settings.runtime.device)
        job_id=uuid.uuid4().hex[:12]; job_dir=Path(self.settings.output.root_dir)/job_id
        ctx=PipelineContext(job_id=job_id,input_path=input_path,job_dir=job_dir,settings=self.settings,device=device)
        PreprocessProcessor().run(ctx)
        if self.settings.pipeline.enable_text: TextProcessor().run(ctx)
        if self.settings.pipeline.enable_geometry: GeometryProcessor().run(ctx); ArrowProcessor().run(ctx)
        ir=CandidateFusionProcessor().run(ctx)
        ir_path=job_dir/"slide_ir.json"; ir.export_json(ir_path)
        pptx=PptxRenderer().render(ir, job_dir/"result.pptx")
        return PipelineResult(job_id, job_dir, pptx, ir_path)
