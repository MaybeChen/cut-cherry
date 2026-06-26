from __future__ import annotations

from image2pptx.models.sam3 import Sam3Adapter
from image2pptx.core.errors import PipelineStageError, format_stage_failure
from image2pptx.pipeline.context import PipelineContext


class Sam3Processor:
    def __init__(self, adapter: Sam3Adapter | None = None) -> None:
        self.adapter = adapter

    def run(self, ctx: PipelineContext) -> None:
        config = getattr(ctx.settings.models, "sam3", {})
        adapter = self.adapter or Sam3Adapter(config, ctx.device)
        regions, warnings = adapter.infer(ctx.artifacts["normalized"])
        ctx.candidates["sam3_regions"] = regions
        if warnings:
            ctx.candidates["sam3_warnings"] = warnings
            raise PipelineStageError(format_stage_failure("sam3", warnings))
        print(
            f"[image2pptx][sam3] regions={len(regions)} warnings={len(warnings)} "
            f"enabled={config.get('enabled', True)}"
        )


class TODOProcessor(Sam3Processor):
    """Backward-compatible alias for the old extension-point class name."""
