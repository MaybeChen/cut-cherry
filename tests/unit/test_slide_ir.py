from PIL import Image

from image2pptx.ir.elements import EditableStrategy, ElementType, Provenance, Rect, SlideElement
from image2pptx.ir.slide_ir import SlideIR


def test_slide_ir_export_load(tmp_path):
    slide = SlideIR(
        width=100,
        height=100,
        elements=[
            SlideElement(
                id="t1",
                type=ElementType.TEXT,
                bbox=Rect(x=1, y=1, width=10, height=10),
                editable_strategy=EditableStrategy.NATIVE_TEXT,
                text="Hi",
            )
        ],
    )
    slide.validate_scene()
    path = tmp_path / "ir.json"
    slide.export_json(path)
    assert SlideIR.load_json(path).elements[0].text == "Hi"


def test_slide_ir_export_serializes_non_json_provenance(tmp_path):
    slide = SlideIR(
        width=100,
        height=100,
        elements=[
            SlideElement(
                id="img",
                type=ElementType.IMAGE,
                bbox=Rect(x=1, y=1, width=10, height=10),
                editable_strategy=EditableStrategy.RASTER_IMAGE,
                provenance=Provenance(
                    source="layout_model",
                    raw={"image": Image.new("RGB", (2, 3), "white")},
                ),
            )
        ],
    )

    path = tmp_path / "ir.json"
    slide.export_json(path)

    assert "<PIL.Image mode=RGB size=(2, 3)>" in path.read_text(encoding="utf-8")
