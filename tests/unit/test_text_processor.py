from image2pptx.processors.text_processor import (
    _build_v2_kwargs,
    _build_v3_kwargs,
    _create_paddleocr,
    _normalize_ocr_result,
)


def test_paddleocr_v3_kwargs_do_not_use_legacy_use_gpu():
    kwargs = _build_v3_kwargs(
        {
            "lang": "ch",
            "det_model_name": "PP-OCRv6_medium_det",
            "rec_model_name": "PP-OCRv6_medium_rec",
            "cls_model_name": "PP-LCNet_x0_25_textline_ori",
            "det_model_dir": "models/ocr/ppocrv6_medium_det",
            "rec_model_dir": "models/ocr/ppocrv6_medium_rec",
            "cls_model_dir": "models/ocr/pp_lcnet_x0_25_textline_ori",
        },
        "cpu",
    )
    assert kwargs["device"] == "cpu"
    assert "use_gpu" not in kwargs
    assert "lang" not in kwargs
    assert kwargs["text_detection_model_name"] == "PP-OCRv6_medium_det"
    assert kwargs["text_detection_model_dir"] == "models/ocr/ppocrv6_medium_det"
    assert kwargs["textline_orientation_model_name"] == "PP-LCNet_x0_25_textline_ori"


def test_paddleocr_v2_kwargs_keep_legacy_use_gpu_for_old_versions():
    kwargs = _build_v2_kwargs({"lang": "ch"}, "cuda")
    assert kwargs["use_gpu"] is True
    assert "device" not in kwargs


def test_create_paddleocr_falls_back_when_v3_rejects_argument():
    calls = []

    class FakePaddleOCR:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            if "device" in kwargs:
                raise ValueError("Unknown argument: device")

    instance, api_version, warnings = _create_paddleocr(FakePaddleOCR, {"lang": "ch"}, "cpu")
    assert instance is not None
    assert api_version == "v2"
    assert warnings[0]["reason"] == "paddleocr_v3_init_failed"
    assert "use_gpu" in calls[1]


def test_normalize_paddleocr_v3_predict_result_dict():
    result = [
        {
            "res": {
                "rec_texts": [" Hello   OCR "],
                "rec_scores": [0.98],
                "rec_polys": [[[1, 2], [11, 2], [11, 7], [1, 7]]],
            }
        }
    ]
    blocks = _normalize_ocr_result(result)
    assert blocks[0]["text"] == "Hello OCR"
    assert blocks[0]["bbox"] == [1.0, 2.0, 11.0, 7.0]


def test_write_ocr_report_records_status_and_items(tmp_path):
    from types import SimpleNamespace

    from image2pptx.processors.text_processor import _write_ocr_report

    ctx = SimpleNamespace(
        job_id="job123",
        job_dir=tmp_path,
        artifacts={},
        candidates={"text": [{"text": "识别成功", "confidence": 0.99, "bbox": [1, 2, 3, 4]}]},
    )
    _write_ocr_report(ctx, status="succeeded", warnings=[])
    report_path = tmp_path / "ocr_results.json"
    assert report_path.exists()
    assert ctx.artifacts["ocr_results"] == report_path
    assert "识别成功" in report_path.read_text(encoding="utf-8")


def test_text_processor_import_warning_module_is_not_shadowed(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import image2pptx.processors.text_processor as text_processor

    class FakeOcr:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def predict(self, path):
            return [
                {
                    "res": {
                        "rec_texts": ["OK"],
                        "rec_scores": [0.9],
                        "rec_polys": [[[0, 0], [10, 0], [10, 5], [0, 5]]],
                    }
                }
            ]

    fake_module = SimpleNamespace(PaddleOCR=FakeOcr)
    monkeypatch.setattr(text_processor.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(text_processor.importlib, "import_module", lambda name: fake_module)

    normalized = tmp_path / "normalized.png"
    normalized.write_bytes(b"fake")
    ctx = SimpleNamespace(
        job_id="job123",
        job_dir=tmp_path,
        artifacts={"normalized": normalized},
        candidates={},
        settings=SimpleNamespace(models=SimpleNamespace(ocr={"allow_auto_download": True})),
        device="cpu",
    )

    text_processor.TextProcessor().run(ctx)

    assert ctx.candidates["text"][0]["text"] == "OK"
    assert (tmp_path / "ocr_results.json").exists()
