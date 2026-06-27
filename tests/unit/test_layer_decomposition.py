from types import SimpleNamespace

from PIL import Image

from image2pptx.ir.candidates import ElementGroup, build_element_groups
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

    element_groups = build_element_groups(layers, candidates)

    assert element_groups["counts"][ElementGroup.CONTAINER.value] == 1
    assert element_groups[ElementGroup.TEXT.value][0]["parent_id"] == layers["containers"][0]["id"]
    assert element_groups[ElementGroup.ASSET.value][0]["raw"]["id"] == "logo"


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
    assert "element_groups" in ctx.candidates
    assert ctx.candidates["element_groups"]["background"][0]["group"] == "background"
    assert ctx.artifacts["layer_decomposition"] == tmp_path / "layer_decomposition.json"
    assert ctx.artifacts["layer_decomposition"].exists()


def test_build_layers_prefers_sam3_mask_for_visual_assets_and_containers():
    candidates = {
        "layout_regions": [
            {
                "id": "coarse",
                "kind": "image_candidate",
                "bbox": [90, 90, 510, 230],
                "confidence": 0.5,
            }
        ],
        "sam3_regions": [
            {
                "id": "sam3_container",
                "kind": "image_candidate",
                "bbox": [100, 100, 500, 220],
                "confidence": 0.9,
                "mask": {"counts": [1], "size": [450, 800]},
            },
            {"id": "sam3_icon", "label": "icon", "bbox": [20, 20, 60, 60], "confidence": 0.95},
        ],
        "text_blocks": [
            {"id": "t1", "text": "A", "bbox": [120, 130, 150, 145], "confidence": 0.9},
            {"id": "t2", "text": "B", "bbox": [220, 130, 250, 145], "confidence": 0.9},
        ],
        "connectors": [
            {"id": "c1", "points": [(130, 150), (250, 150)], "confidence": 0.8},
            {"id": "c2", "points": [(130, 170), (250, 170)], "confidence": 0.8},
            {"id": "c3", "points": [(130, 190), (250, 190)], "confidence": 0.8},
        ],
    }

    layers = build_layers(candidates, (800, 450))

    assert layers["containers"][0]["source"] == "sam3"
    assert layers["containers"][0]["style"]["corner_radius"] > 0
    assert any(
        asset["id"] == "sam3_icon" and asset["kind"] == "icon_candidate"
        for asset in layers["assets"]
    )
