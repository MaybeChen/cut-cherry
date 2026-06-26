import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from image2pptx.models import layout as layout_model
from image2pptx.models.layout import LayoutModelAdapter, _predict, normalize_layout_result
from image2pptx.processors.layout_parser import LayoutParserProcessor


def test_normalize_layout_result_maps_common_regions():
    regions = normalize_layout_result(
        {
            "res": {
                "layout_det_res": [
                    {"label": "table", "bbox": [1, 2, 11, 12], "score": 0.9},
                    {"type": "figure", "coordinate": [[20, 20], [40, 20], [40, 30], [20, 30]]},
                ]
            }
        }
    )

    assert regions[0]["kind"] == "table_candidate"
    assert regions[0]["bbox"] == [1.0, 2.0, 11.0, 12.0]
    assert regions[1]["kind"] == "image_candidate"
    assert regions[1]["bbox"] == [20.0, 20.0, 40.0, 30.0]


def test_layout_adapter_reports_missing_local_model(monkeypatch):
    monkeypatch.setattr(layout_model.importlib.util, "find_spec", lambda name: object())
    adapter = LayoutModelAdapter({"engine": "pp_structure_v3", "allow_auto_download": False}, "cpu")

    available, warnings = adapter.available()

    assert available is False
    assert warnings[0]["reason"] == "local_layout_model_missing"


def test_layout_adapter_uses_ppstructurev3_predict(monkeypatch, tmp_path):
    class FakePPStructureV3:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def predict(self, input, **kwargs):
            return [{"label": "title", "bbox": [10, 10, 80, 30], "score": 0.88, "text": "Title"}]

    fake_module = SimpleNamespace(PPStructureV3=FakePPStructureV3)
    monkeypatch.setattr(layout_model.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(layout_model.importlib, "import_module", lambda name: fake_module)
    image = tmp_path / "page.png"
    image.write_bytes(b"fake")

    adapter = LayoutModelAdapter({"engine": "pp_structure_v3", "allow_auto_download": True}, "cpu")
    regions, warnings = adapter.infer(image)

    assert warnings == []
    assert regions[0]["kind"] == "title"
    assert regions[0]["text"] == "Title"


def test_layout_adapter_does_not_pass_layout_model_dir_with_paddlex_config(monkeypatch, tmp_path):
    calls = []

    class FakePPStructureV3:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            if "layout_model_dir" in kwargs:
                raise ValueError("Unknown argument: layout_model_dir")

        def predict(self, input, **kwargs):
            return [{"label": "title", "bbox": [10, 10, 80, 30], "score": 0.88}]

    fake_module = SimpleNamespace(PPStructureV3=FakePPStructureV3)
    monkeypatch.setattr(layout_model.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(layout_model.importlib, "import_module", lambda name: fake_module)
    config_path = tmp_path / "PP-StructureV3.yaml"
    config_path.write_text("pipeline: PP-StructureV3\n", encoding="utf-8")
    image = tmp_path / "page.png"
    image.write_bytes(b"fake")

    adapter = LayoutModelAdapter(
        {
            "engine": "pp_structure_v3",
            "allow_auto_download": False,
            "paddlex_config": str(config_path),
            "layout_model_dir": str(tmp_path / "legacy_layout_model_dir"),
        },
        "cpu",
    )
    regions, warnings = adapter.infer(image)

    assert warnings == []
    assert regions[0]["kind"] == "title"
    assert "layout_model_dir" not in calls[0]
    assert calls[0]["paddlex_config"] == str(config_path)


def test_layout_predict_reports_missing_chart_model_when_enabled(tmp_path) -> None:
    class FakePipeline:
        def predict(self, input, **kwargs):
            return []

    image = tmp_path / "page.png"
    image.write_bytes(b"fake")

    try:
        _predict(FakePipeline(), image, {"use_chart_recognition": True})
    except RuntimeError as exc:
        assert "layout_chart_recognition_model_missing" in str(exc)
        assert "use_chart_recognition=false" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected missing chart model to fail fast")


def test_layout_parser_writes_model_report_and_merges_rules(tmp_path, monkeypatch):
    normalized = tmp_path / "normalized.png"
    normalized.write_bytes(b"fake")

    def fake_infer(self, image_path: Path):
        return [
            {
                "id": "layout_model_0",
                "kind": "title",
                "bbox": [10, 10, 100, 40],
                "confidence": 0.9,
                "text": "Model title",
            }
        ], []

    monkeypatch.setattr(LayoutModelAdapter, "infer", fake_infer)
    ctx = SimpleNamespace(
        job_id="job123",
        job_dir=tmp_path,
        artifacts={"normalized": normalized},
        device="cpu",
        settings=SimpleNamespace(models=SimpleNamespace(layout={"engine": "pp_structure_v3"})),
        candidates={
            "text": [
                {"id": "text_0", "text": "Body", "bbox": [10, 80, 80, 100], "confidence": 0.8}
            ],
            "lines": [],
            "shapes": [],
        },
    )

    LayoutParserProcessor().run(ctx)

    assert ctx.candidates["layout_regions"][0]["text"] == "Model title"
    assert (tmp_path / "layout_results.json").exists()
    assert ctx.artifacts["layout_results"] == tmp_path / "layout_results.json"
    report = json.loads((tmp_path / "layout_results.json").read_text(encoding="utf-8"))
    assert report["kind_counts"] == {"title": 1, "text_line": 1}


def test_layout_report_serializes_non_json_raw_values(tmp_path, monkeypatch):
    normalized = tmp_path / "normalized.png"
    normalized.write_bytes(b"fake")

    def fake_infer(self, image_path: Path):
        return [
            {
                "id": "layout_model_0",
                "kind": "image_candidate",
                "bbox": [10, 10, 100, 40],
                "confidence": 0.9,
                "raw": {"image": Image.new("RGB", (2, 3), "white")},
            }
        ], []

    monkeypatch.setattr(LayoutModelAdapter, "infer", fake_infer)
    ctx = SimpleNamespace(
        job_id="job_raw_image",
        job_dir=tmp_path,
        artifacts={"normalized": normalized},
        device="cpu",
        settings=SimpleNamespace(models=SimpleNamespace(layout={"engine": "pp_structure_v3"})),
        candidates={"text": [], "lines": [], "shapes": []},
    )

    LayoutParserProcessor().run(ctx)

    report = json.loads((tmp_path / "layout_results.json").read_text(encoding="utf-8"))
    assert report["items"][0]["raw"]["image"] == "<PIL.Image mode=RGB size=(2, 3)>"


def test_paddleocr_vl_uses_local_paddlex_config(monkeypatch, tmp_path):
    calls = []

    class FakePipeline:
        def predict(self, input, **kwargs):
            return [{"label": "table", "bbox": [1, 2, 3, 4], "score": 0.8}]

    def fake_create_pipeline(**kwargs):
        calls.append(kwargs)
        return FakePipeline()

    fake_paddlex = SimpleNamespace(create_pipeline=fake_create_pipeline)

    def fake_find_spec(name):
        return object() if name == "paddlex" else None

    monkeypatch.setattr(layout_model.importlib.util, "find_spec", fake_find_spec)
    monkeypatch.setattr(layout_model.importlib, "import_module", lambda name: fake_paddlex)
    config_path = tmp_path / "PaddleOCR-VL.yaml"
    config_path.write_text("pipeline: PaddleOCR-VL\n", encoding="utf-8")
    image = tmp_path / "page.png"
    image.write_bytes(b"fake")

    adapter = LayoutModelAdapter(
        {
            "engine": "paddleocr_vl",
            "allow_auto_download": False,
            "paddlex_config": str(config_path),
        },
        "cpu",
    )
    regions, warnings = adapter.infer(image)

    assert warnings == []
    assert calls == [{"pipeline": str(config_path)}]
    assert regions[0]["kind"] == "table_candidate"


def test_layout_adapter_accepts_local_paddleocr_vl_model_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(layout_model.importlib.util, "find_spec", lambda name: object())
    model_dir = tmp_path / "paddleocr_vl"
    model_dir.mkdir()
    adapter = LayoutModelAdapter(
        {
            "engine": "paddleocr_vl",
            "allow_auto_download": False,
            "paddleocr_vl_model_dir": str(model_dir),
        },
        "cpu",
    )

    available, warnings = adapter.available()

    assert available is True
    assert warnings == []


def test_layout_adapter_reports_missing_paddlex_config(monkeypatch, tmp_path):
    monkeypatch.setattr(layout_model.importlib.util, "find_spec", lambda name: object())
    missing_config = tmp_path / "missing.yaml"
    adapter = LayoutModelAdapter(
        {
            "engine": "pp_structure_v3",
            "allow_auto_download": False,
            "paddlex_config": str(missing_config),
        },
        "cpu",
    )

    available, warnings = adapter.available()

    assert available is False
    assert warnings[0]["reason"] == "local_layout_paddlex_config_missing"
    assert warnings[0]["paddlex_config"] == str(missing_config)


def test_normalize_layout_result_maps_icon_and_logo_labels() -> None:
    from image2pptx.models.layout import normalize_layout_result

    regions = normalize_layout_result(
        [
            {"label": "icon", "bbox": [1, 2, 11, 12], "score": 0.8},
            {"label": "logo", "bbox": [20, 2, 60, 22], "score": 0.9},
        ]
    )

    assert regions[0]["kind"] == "icon_candidate"
    assert regions[1]["kind"] == "logo_candidate"


def test_normalize_layout_result_accepts_paddlex_nested_region_schema() -> None:
    regions = normalize_layout_result(
        {
            "page": {
                "parsing_res_list": [
                    {
                        "block_label": "图片",
                        "layout_bbox": [100, 80, 260, 200],
                        "layout_score": 0.83,
                        "region_id": "figure_a",
                    },
                    {
                        "layout_type": "标题",
                        "poly": [[20, 10], [180, 10], [180, 42], [20, 42]],
                        "det_score": 0.91,
                        "content": "Quarterly Report",
                    },
                ]
            }
        }
    )

    assert regions[0]["kind"] == "image_candidate"
    assert regions[0]["source_ids"] == ["figure_a"]
    assert regions[0]["confidence"] == 0.83
    assert regions[1]["kind"] == "title"
    assert regions[1]["bbox"] == [20.0, 10.0, 180.0, 42.0]
    assert regions[1]["polygon"] == [[20.0, 10.0], [180.0, 10.0], [180.0, 42.0], [20.0, 42.0]]
    assert regions[1]["text"] == "Quarterly Report"
