from __future__ import annotations
from image2pptx.pipeline.context import PipelineContext


class TODOProcessor:
    """Phase 2-5 extension point; not wired into the fail-fast pipeline yet."""

    def run(self, ctx: PipelineContext) -> None:
        return None
