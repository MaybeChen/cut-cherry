from types import SimpleNamespace

from PIL import Image, ImageDraw

from image2pptx.processors.text_layer import TextLayerProcessor, build_text_layer


def test_build_text_layer_adds_role_size_and_sampled_color():
    image = Image.new("RGB", (300, 120), "white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 10), "Title", fill=(10, 20, 30))
    blocks = [{"id": "t", "text": "Title", "bbox": [18, 8, 180, 34], "confidence": 0.9}]

    layer = build_text_layer(blocks, image)

    assert layer[0]["text_role"] == "title"
    assert layer[0]["font_size"] >= 10
    assert layer[0]["font_color"].startswith("#")


def test_text_layer_processor_writes_report(tmp_path):
    normalized = tmp_path / "normalized.png"
    Image.new("RGB", (100, 60), "white").save(normalized)
    ctx = SimpleNamespace(
        job_dir=tmp_path,
        artifacts={"normalized": normalized},
        candidates={"text": [{"id": "t", "text": "Label", "bbox": [5, 5, 40, 16], "confidence": 0.9}]},
    )

    TextLayerProcessor().run(ctx)

    assert ctx.candidates["text_layer"][0]["layer_kind"] == "text"
    assert ctx.artifacts["text_layer"].exists()
