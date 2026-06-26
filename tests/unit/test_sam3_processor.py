from types import SimpleNamespace
import warnings

from image2pptx.models import sam3 as sam3_model
from image2pptx.models.sam3 import (
    Sam3Adapter,
    _ensure_sam3_source_on_path,
    _import_sam3_image_processor,
    normalize_sam3_result,
)
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
    regions = normalize_sam3_result(
        {"results": [{"prompt": "figure", "polygon": [[4, 8], [9, 3]]}]}
    )

    assert regions[0]["bbox"] == [4.0, 3.0, 9.0, 8.0]
    assert regions[0]["kind"] == "image_candidate"


def test_ensure_sam3_source_on_path_accepts_banana_sam3_src(tmp_path, monkeypatch) -> None:
    sam3_src = tmp_path / "sam3_src"
    (sam3_src / "sam3").mkdir(parents=True)
    monkeypatch.syspath_prepend(str(tmp_path / "existing"))

    resolved = _ensure_sam3_source_on_path({"sam3_src_path": str(sam3_src)})

    assert resolved == sam3_src.resolve()
    import sys

    assert sys.path[0] == str(sam3_src.resolve())


def test_sam3_adapter_reports_missing_configured_assets(tmp_path) -> None:
    image = tmp_path / "normalized.png"
    image.write_bytes(b"fake")

    regions, warnings = Sam3Adapter(
        {
            "enabled": True,
            "model_path": str(tmp_path / "models" / "sam3.pt"),
            "bpe_path": str(tmp_path / "models" / "bpe_simple_vocab_16e6.txt.gz"),
        },
        "cpu",
    ).infer(image)

    assert regions == []
    assert [warning["reason"] for warning in warnings] == [
        "sam3_asset_missing",
        "sam3_asset_missing",
    ]
    assert warnings[0]["key"] == "model_path"


def test_sam3_adapter_reports_missing_runtime_modules_before_runtime_init(
    tmp_path, monkeypatch
) -> None:
    image = tmp_path / "normalized.png"
    image.write_bytes(b"fake")
    model_path = tmp_path / "models" / "sam3.pt"
    bpe_path = tmp_path / "models" / "bpe_simple_vocab_16e6.txt.gz"
    model_path.parent.mkdir()
    model_path.write_bytes(b"fake")
    bpe_path.write_bytes(b"fake")

    def fake_find_spec(name: str):
        if name == "sam3":
            return object()
        if name in {"triton", "pycocotools"}:
            return None
        return object()

    monkeypatch.setattr(sam3_model.importlib.util, "find_spec", fake_find_spec)

    regions, warnings = Sam3Adapter(
        {
            "enabled": True,
            "model_path": str(model_path),
            "bpe_path": str(bpe_path),
        },
        "cpu",
    ).infer(image)

    assert regions == []
    assert [warning["reason"] for warning in warnings] == [
        "sam3_triton_missing",
        "sam3_pycocotools_missing",
    ]
    assert [warning["module"] for warning in warnings] == ["triton", "pycocotools"]


def test_sam3_image_processor_import_suppresses_cpu_optional_warnings(monkeypatch) -> None:
    def fake_import_module(name: str):
        warnings.warn(
            "CUDA is not available or torch_xla is imported. Disabling autocast.", UserWarning
        )
        warnings.warn(
            "Importing from timm.models.layers is deprecated, please import via timm.layers",
            FutureWarning,
        )
        return SimpleNamespace(name=name)

    monkeypatch.setattr(sam3_model.importlib, "import_module", fake_import_module)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        module = _import_sam3_image_processor()

    assert module.name == "sam3.model.sam3_image_processor"
    assert caught == []
