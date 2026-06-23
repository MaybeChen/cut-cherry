from __future__ import annotations
import cv2
from image2pptx.pipeline.context import PipelineContext

class TextProcessor:
    def run(self, ctx: PipelineContext) -> None:
        # Phase 1 降级 OCR：若 PaddleOCR 未安装，则保留空结果，链路继续输出可编辑形状。
        blocks: list[dict] = []
        try:
            from paddleocr import PaddleOCR  # type: ignore
            ocr = PaddleOCR(use_angle_cls=True, lang=ctx.settings.models.ocr.get("lang", "ch"), use_gpu=ctx.device == "cuda")
            result = ocr.ocr(str(ctx.artifacts["normalized"]), cls=True)
            for i, line in enumerate(result[0] if result else []):
                pts, (text, conf) = line
                xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
                blocks.append({"id":f"text_{i}","text":text,"bbox":[min(xs),min(ys),max(xs),max(ys)],"confidence":float(conf)})
        except ImportError:
            # 明确降级：无 OCR 模型时不伪造文本。
            blocks = []
        ctx.candidates["text"] = blocks
