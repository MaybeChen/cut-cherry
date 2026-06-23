from image2pptx.ir.slide_ir import SlideIR

def validate_slide_ir(slide: SlideIR) -> None:
    slide.validate_scene()
