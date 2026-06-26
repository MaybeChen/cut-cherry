from types import SimpleNamespace
import sys

sys.modules.setdefault("cv2", SimpleNamespace())

from image2pptx.pipeline.orchestrator import _summarize_degradation  # noqa: E402


def test_summarize_degradation_includes_warning_details() -> None:
    ctx = SimpleNamespace(
        candidates={
            "sam3_warnings": [
                {
                    "reason": "sam3_asset_missing",
                    "message": "Configured models.sam3.model_path does not exist: models/sam3/sam3.pt",
                }
            ]
        }
    )

    lines = _summarize_degradation(ctx, "sam3")

    assert "sam3_asset_missing" in lines[0]
    assert "models/sam3/sam3.pt" in lines[0]
    assert lines[1].startswith("fallback=")
