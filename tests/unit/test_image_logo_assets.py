from PIL import Image

from image2pptx.processors.layout_parser import _detect_image_candidates, _get_slide_size


def test_detect_image_candidates_marks_small_corner_asset_as_logo() -> None:
    regions = _detect_image_candidates(
        [
            {
                "id": "shape_logo",
                "bbox": [16, 12, 96, 58],
                "confidence": 0.52,
            }
        ],
        text_blocks=[],
        slide_size=(400, 300),
    )

    assert regions[0]["kind"] == "logo_candidate"
    assert regions[0]["id"] == "logo_candidate_0"
    assert regions[0]["confidence"] == 0.55


def test_detect_image_candidates_keeps_large_asset_as_image() -> None:
    regions = _detect_image_candidates(
        [
            {
                "id": "shape_photo",
                "bbox": [80, 80, 320, 240],
                "confidence": 0.8,
            }
        ],
        text_blocks=[],
        slide_size=(400, 300),
    )

    assert regions[0]["kind"] == "image_candidate"
    assert regions[0]["confidence"] == 0.6


def test_get_slide_size_reads_normalized_artifact(tmp_path) -> None:
    normalized = tmp_path / "normalized.png"
    Image.new("RGB", (640, 360), "white").save(normalized)
    ctx = type("Ctx", (), {"artifacts": {"normalized": normalized}})()

    assert _get_slide_size(ctx) == (640, 360)


def test_detect_raster_icon_candidates_from_foreground_components(tmp_path) -> None:
    from types import SimpleNamespace

    from PIL import ImageDraw

    from image2pptx.processors.layout_parser import _detect_raster_icon_candidates

    normalized = tmp_path / "normalized.png"
    image = Image.new("RGB", (240, 160), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((40, 35, 72, 67), fill="#1f77b4")
    draw.rectangle((47, 42, 65, 60), fill="white")
    image.save(normalized)
    ctx = SimpleNamespace(artifacts={"normalized": normalized})

    regions = _detect_raster_icon_candidates(ctx, text_blocks=[], slide_size=(240, 160))

    assert regions
    assert regions[0]["kind"] == "icon_candidate"
    assert regions[0]["bbox"][0] <= 42
    assert regions[0]["bbox"][2] >= 70


def test_detect_raster_icon_candidates_with_dark_frame_and_nearby_text(tmp_path) -> None:
    from types import SimpleNamespace

    from PIL import ImageDraw

    from image2pptx.processors.layout_parser import _detect_raster_icon_candidates

    normalized = tmp_path / "normalized.png"
    image = Image.new("RGB", (320, 180), "#f7fbff")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 319, 8), fill="#111827")
    draw.rectangle((0, 172, 319, 179), fill="#111827")
    draw.ellipse((42, 42, 76, 76), fill="#2563eb")
    draw.ellipse((52, 52, 66, 66), outline="white", width=2)
    # Simulate nearby dark label glyphs; these should not merge with/suppress the icon.
    draw.rectangle((84, 48, 90, 68), fill="#0f172a")
    draw.rectangle((94, 48, 100, 68), fill="#0f172a")
    image.save(normalized)
    ctx = SimpleNamespace(artifacts={"normalized": normalized})

    regions = _detect_raster_icon_candidates(ctx, text_blocks=[], slide_size=(320, 180))

    assert regions
    assert regions[0]["kind"] == "icon_candidate"
    assert regions[0]["bbox"][0] <= 44
    assert regions[0]["bbox"][2] < 84
