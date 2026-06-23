from __future__ import annotations
from PIL import Image
from image2pptx.ir.elements import EditableStrategy, ElementStyle, ElementType, Provenance, Rect, SlideElement
from image2pptx.ir.slide_ir import SlideIR
from image2pptx.pipeline.context import PipelineContext

class CandidateFusionProcessor:
    def run(self, ctx: PipelineContext) -> SlideIR:
        im = Image.open(ctx.artifacts["normalized"])
        slide = SlideIR(width=im.width, height=im.height)
        # 简单背景使用原生纯色，避免整页原图伪背景。
        slide.elements.append(SlideElement(id="background", type=ElementType.BACKGROUND, bbox=Rect(x=0,y=0,width=im.width,height=im.height), z_index=0, style=ElementStyle(fill_color="#ffffff"), provenance=Provenance(source="background_processor"), editable_strategy=EditableStrategy.NATIVE_SHAPE))
        for s in ctx.candidates.get("shapes", []):
            x1,y1,x2,y2=s["bbox"]
            slide.elements.append(SlideElement(id=s["id"], type=ElementType.SHAPE, bbox=Rect(x=x1,y=y1,width=x2-x1,height=y2-y1), z_index=10, style=ElementStyle(fill_color=s.get("fill_color"), line_color="#666666", shape_type=s.get("kind")), confidence=s["confidence"], provenance=Provenance(source="opencv", raw=s), editable_strategy=EditableStrategy.NATIVE_SHAPE))
        for t in ctx.candidates.get("text", []):
            x1,y1,x2,y2=t["bbox"]
            slide.elements.append(SlideElement(id=t["id"], type=ElementType.TEXT, bbox=Rect(x=x1,y=y1,width=x2-x1,height=y2-y1), z_index=50, text=t["text"], confidence=t["confidence"], provenance=Provenance(source="ocr", raw=t), editable_strategy=EditableStrategy.NATIVE_TEXT))
        for c in ctx.candidates.get("connectors", [])[:50]:
            (x1,y1),(x2,y2)=c["points"]
            slide.elements.append(SlideElement(id=c["id"], type=ElementType.CONNECTOR, bbox=Rect(x=min(x1,x2),y=min(y1,y2),width=abs(x2-x1) or 1,height=abs(y2-y1) or 1), z_index=20, style=ElementStyle(line_color="#000000"), confidence=c["confidence"], provenance=Provenance(source="opencv_hough", raw=c), editable_strategy=EditableStrategy.NATIVE_CONNECTOR))
        slide.validate_scene(); slide.relations.extend(slide.find_overlaps(0.2)); return slide
