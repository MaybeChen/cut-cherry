from __future__ import annotations

from pathlib import Path

MODEL_ROOT = Path("models")
OCR_ROOT = MODEL_ROOT / "ocr"

RECOMMENDED_OCR_MODELS = {
    "det": "PP-OCRv6_medium_det",
    "rec": "PP-OCRv6_medium_rec",
    "cls": "PP-LCNet_x0_25_textline_ori",
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

    print("Manual model download only; no weights were downloaded.")
    print("Recommended OCR models for CPU-first PPT screenshots:")
    for role, model_name in RECOMMENDED_OCR_MODELS.items():
        print(f"  {role}: {model_name}")
    print("Place Paddle inference files under:")
    print("  models/ocr/ppocrv6_medium_det/")
    print("  models/ocr/ppocrv6_medium_rec/")
    print("  models/ocr/pp_lcnet_x0_25_textline_ori/")
    print("Each PP-OCRv6/PaddlePaddle 3.x inference folder should contain files such as inference.json, inference.pdiparams, and inference.yml.")


if __name__ == "__main__":
    main()
