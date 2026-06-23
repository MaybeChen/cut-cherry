from __future__ import annotations
from image2pptx.pipeline.context import PipelineContext

class TODOProcessor:
    """Phase 2-5 extension point; current implementation is an explicit no-op fallback."""
    def run(self, ctx: PipelineContext) -> None:
        return None
