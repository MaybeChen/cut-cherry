from types import SimpleNamespace

import numpy as np
from PIL import Image

from image2pptx.models import rmbg as rmbg_model
from image2pptx.models.rmbg import RmbgAdapter


def test_rmbg_adapter_reports_unavailable_without_model(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(rmbg_model.importlib.util, "find_spec", lambda name: None)
    adapter = RmbgAdapter({"enabled": True, "model_path": str(tmp_path / "missing.onnx")})

    alpha, warnings = adapter.infer_alpha(Image.new("RGB", (8, 8), "white"))

    assert alpha is None
    assert warnings[0]["reason"] == "rmbg_not_available"


def test_rmbg_adapter_runs_generic_onnx_alpha(monkeypatch, tmp_path) -> None:
    model_path = tmp_path / "rmbg.onnx"
    model_path.write_bytes(b"fake")

    class FakeSession:
        def get_inputs(self):
            return [SimpleNamespace(name="input")]

        def run(self, _outputs, inputs):
            assert "input" in inputs
            return [np.ones((1, 1, 4, 4), dtype="float32")]

    fake_ort = SimpleNamespace(
        get_available_providers=lambda: ["CPUExecutionProvider"],
        InferenceSession=lambda path, providers: FakeSession(),
    )
    monkeypatch.setattr(rmbg_model.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(rmbg_model.importlib, "import_module", lambda name: fake_ort)

    adapter = RmbgAdapter({"enabled": True, "model_path": str(model_path), "input_size": 4})
    alpha, warnings = adapter.infer_alpha(Image.new("RGB", (6, 5), "white"))

    assert warnings == []
    assert alpha is not None
    assert alpha.size == (6, 5)
    assert alpha.getpixel((0, 0)) == 255
