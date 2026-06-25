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
