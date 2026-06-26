from __future__ import annotations
from image2pptx.pipeline.context import PipelineContext


class ArrowProcessor:
    def run(self, ctx: PipelineContext) -> None:
        # Phase 1 基础 connector：Hough 线段转原生线；箭头头部/吸附在 Phase 3 增强。
        ctx.candidates["connectors"] = [
            {**line, "begin_arrow": None, "end_arrow": None}
            for line in ctx.candidates.get("lines", [])
        ]
