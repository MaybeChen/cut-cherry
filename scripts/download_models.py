from __future__ import annotations

from pathlib import Path

MODEL_ROOT = Path("models")
OCR_ROOT = MODEL_ROOT / "ocr"
LAYOUT_ROOT = MODEL_ROOT / "layout"

RECOMMENDED_OCR_MODELS = {
    "det": "PP-OCRv6_medium_det",
    "rec": "PP-OCRv6_medium_rec",
    "cls": "PP-LCNet_x0_25_textline_ori",
}

RECOMMENDED_LAYOUT_MODELS = {
    "pp_structure_v3": "PP-StructureV3 PaddleX pipeline config + local model folders",
    "paddleocr_vl": "PaddlePaddle/PaddleOCR-VL-1.6 or PaddlePaddle/PaddleOCR-VL",
}


def main() -> None:
    """Create local model folders and print the manual download plan.

    This script intentionally does not fetch weights automatically. Production and
    offline environments should download vetted model artifacts separately and then
    place them under ./models.
    """
    OCR_ROOT.mkdir(parents=True, exist_ok=True)
    for dirname in ("ppocrv6_medium_det", "ppocrv6_medium_rec", "pp_lcnet_x0_25_textline_ori"):
        (OCR_ROOT / dirname).mkdir(parents=True, exist_ok=True)

    LAYOUT_ROOT.mkdir(parents=True, exist_ok=True)
    for dirname in ("pp_structure_v3", "paddleocr_vl"):
        (LAYOUT_ROOT / dirname).mkdir(parents=True, exist_ok=True)

    print("Manual model download only; no weights were downloaded.")
    print("Recommended OCR models for CPU-first PPT screenshots:")
    for role, model_name in RECOMMENDED_OCR_MODELS.items():
        print(f"  {role}: {model_name}")
    print("Place Paddle inference files under:")
    print("  models/ocr/ppocrv6_medium_det/")
    print("  models/ocr/ppocrv6_medium_rec/")
    print("  models/ocr/pp_lcnet_x0_25_textline_ori/")
    print(
        "Each PP-OCRv6/PaddlePaddle 3.x inference folder should contain files such as "
        "inference.json, inference.pdiparams, and inference.yml."
    )
    print()
    print("Recommended layout model locations:")
    for engine, description in RECOMMENDED_LAYOUT_MODELS.items():
        print(f"  {engine}: {description}")
    print("Create/download layout assets under:")
    print("  models/layout/pp_structure_v3/")
    print("  models/layout/paddleocr_vl/")
    print("Example Hugging Face download command for PaddleOCR-VL:")
    print(
        "  huggingface-cli download PaddlePaddle/PaddleOCR-VL-1.6 "
        "--local-dir models/layout/paddleocr_vl"
    )
    print("Point models.layout.paddlex_config to a local PaddleX YAML that references this folder.")


if __name__ == "__main__":
    main()
