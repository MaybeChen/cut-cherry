from types import SimpleNamespace

from image2pptx.models.sam3 import normalize_sam3_result
from image2pptx.processors.sam3_processor import Sam3Processor


class FakeSam3Adapter:
    def infer(self, image_path):
        return [
            {
                "id": "sam3_0",
                "kind": "icon_candidate",
                "bbox": [10, 10, 30, 30],
                "confidence": 0.8,
                "source": "sam3",
            }
        ], []


def test_normalize_sam3_result_maps_visual_prompts() -> None:
    regions = normalize_sam3_result(
        {
            "regions": [
                {"concept": "icon", "bbox": [1, 2, 11, 12], "score": 0.8},
                {"concept": "company logo", "bbox": [20, 2, 60, 22], "score": 0.9},
                {"concept": "illustration", "bbox": [70, 2, 110, 42], "score": 0.7},
            ]
        }
    )

    assert [region["kind"] for region in regions] == [
        "icon_candidate",
        "logo_candidate",
        "image_candidate",
    ]


def test_sam3_processor_stores_regions_and_prints_summary(tmp_path, capsys) -> None:
    normalized = tmp_path / "normalized.png"
    normalized.write_bytes(b"fake")
    ctx = SimpleNamespace(
        device="cpu",
        artifacts={"normalized": normalized},
        candidates={},
        settings=SimpleNamespace(models=SimpleNamespace(sam3={"enabled": True})),
    )

    Sam3Processor(adapter=FakeSam3Adapter()).run(ctx)

    assert ctx.candidates["sam3_regions"][0]["kind"] == "icon_candidate"
    assert "[image2pptx][sam3] regions=1 warnings=0" in capsys.readouterr().out


def test_normalize_sam3_result_accepts_edit_banana_results_schema() -> None:
    regions = normalize_sam3_result(
        {
            "image_size": {"width": 100, "height": 50},
            "results": [
                {
                    "prompt": "diagram symbol",
                    "score": 0.91,
                    "bbox": [40, 30, 10, 5],
                    "polygon": [[10, 5], [40, 5], [40, 30], [10, 30]],
                    "mask": {"format": "rle", "data": "5,2,3", "shape": [50, 100]},
                }
            ],
        }
    )

    assert regions == [
        {
            "id": "sam3_0",
            "kind": "icon_candidate",
            "bbox": [10.0, 5.0, 40.0, 30.0],
            "confidence": 0.91,
            "source": "sam3",
            "raw": {
                "prompt": "diagram symbol",
                "score": 0.91,
                "bbox": [40, 30, 10, 5],
                "polygon": [[10, 5], [40, 5], [40, 30], [10, 30]],
                "mask": {"format": "rle", "data": "5,2,3", "shape": [50, 100]},
            },
            "polygon": [[10, 5], [40, 5], [40, 30], [10, 30]],
            "mask": {"format": "rle", "data": "5,2,3", "shape": [50, 100]},
        }
    ]


def test_normalize_sam3_result_derives_bbox_from_polygon() -> None:
    regions = normalize_sam3_result({"results": [{"prompt": "figure", "polygon": [[4, 8], [9, 3]]}]})

    assert regions[0]["bbox"] == [4.0, 3.0, 9.0, 8.0]
    assert regions[0]["kind"] == "image_candidate"
