from types import SimpleNamespace

from PIL import Image

from image2pptx.processors.layer_decomposition import LayerDecompositionProcessor, build_layers


def test_build_layers_separates_containers_assets_and_assigns_text_parent():
    candidates = {
        "layout_regions": [
            {
                "id": "module_image",
                "kind": "image_candidate",
                "bbox": [100, 100, 500, 220],
                "confidence": 0.8,
                "source": "layout_model",
            },
            {
                "id": "logo",
                "kind": "logo_candidate",
                "bbox": [10, 10, 50, 50],
                "confidence": 0.8,
            },
        ],
        "text_blocks": [
            {"id": "text_0", "text": "Agent", "bbox": [120, 130, 170, 150], "confidence": 0.9},
            {"id": "text_1", "text": "Skill", "bbox": [220, 130, 270, 150], "confidence": 0.9},
            {"id": "text_2", "text": "Guard", "bbox": [320, 130, 370, 150], "confidence": 0.9},
        ],
        "shapes": [],
        "connectors": [],
    }

    layers = build_layers(candidates, (800, 450))

    assert layers["counts"] == {"containers": 1, "texts": 3, "assets": 1, "connectors": 0}
    assert layers["containers"][0]["source_id"] == "module_image"
    assert layers["assets"][0]["id"] == "logo"
    assert layers["texts"][0]["parent_id"] == layers["containers"][0]["id"]


def test_layer_decomposition_processor_writes_report(tmp_path):
    normalized = tmp_path / "normalized.png"
    Image.new("RGB", (100, 60), "white").save(normalized)
    ctx = SimpleNamespace(
        job_dir=tmp_path,
        artifacts={"normalized": normalized},
        candidates={"layout_regions": [], "text_blocks": [], "shapes": [], "connectors": []},
    )

    LayerDecompositionProcessor().run(ctx)

    assert "layers" in ctx.candidates
    assert ctx.artifacts["layer_decomposition"] == tmp_path / "layer_decomposition.json"
    assert ctx.artifacts["layer_decomposition"].exists()
