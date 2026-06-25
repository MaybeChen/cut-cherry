import json
from types import SimpleNamespace

from PIL import Image

from image2pptx.ir.elements import ElementType
from image2pptx.processors.candidate_fusion import CandidateFusionProcessor


def test_candidate_fusion_promotes_layout_regions_to_table_and_image(tmp_path):
    normalized = tmp_path / "normalized.png"
    Image.new("RGB", (300, 200), "white").save(normalized)
    ctx = SimpleNamespace(
        job_dir=tmp_path,
        artifacts={"normalized": normalized},
        candidates={
            "layout_regions": [
                {
                    "id": "table_candidate_0",
                    "kind": "table_candidate",
                    "bbox": [10, 10, 110, 70],
                    "confidence": 0.65,
                    "rows": 1,
                    "cols": 1,
                    "cells": [[{"row": 0, "col": 0, "text": "Cell", "source_ids": ["text_0"]}]],
                },
                {
                    "id": "image_candidate_0",
                    "kind": "image_candidate",
                    "bbox": [150, 20, 260, 150],
                    "confidence": 0.5,
                    "source_ids": ["shape_0"],
                },
            ],
            "text_blocks": [
                {
                    "id": "text_block_0",
                    "kind": "paragraph",
                    "text": "Cell",
                    "bbox": [20, 20, 80, 40],
                    "confidence": 0.9,
                }
            ],
            "shapes": [
                {
                    "id": "shape_0",
                    "kind": "rectangle",
                    "bbox": [150, 20, 260, 150],
                    "fill_color": "#ffffff",
                    "confidence": 0.6,
                }
            ],
            "formulas": [
                {
                    "id": "formula_0",
                    "kind": "formula",
                    "text": "E = mc^2",
                    "bbox": [20, 80, 100, 110],
                    "confidence": 0.8,
                }
            ],
            "charts": [
                {
                    "id": "chart_0",
                    "kind": "bar_chart",
                    "bbox": [30, 120, 130, 190],
                    "confidence": 0.7,
                    "categories": ["1", "2", "3"],
                    "values": [0.5, 1.0, 0.75],
                    "source_ids": [],
                }
            ],
            "connectors": [],
        },
    )

    slide = CandidateFusionProcessor().run(ctx)
    element_types = {element.id: element.type for element in slide.elements}

    assert element_types["table_candidate_0"] == ElementType.TABLE
    assert element_types["image_candidate_0"] == ElementType.IMAGE
    assert element_types["formula_0"] == ElementType.FORMULA
    assert element_types["chart_0"] == ElementType.CHART
    assert "text_block_0" not in element_types
    assert "shape_0" not in element_types
    assert (tmp_path / "assets" / "images" / "image_candidate_0.png").exists()


def test_candidate_fusion_exports_logo_assets_separately(tmp_path, capsys):
    normalized = tmp_path / "normalized.png"
    Image.new("RGB", (400, 300), "white").save(normalized)
    ctx = SimpleNamespace(
        job_dir=tmp_path,
        artifacts={"normalized": normalized},
        candidates={
            "layout_regions": [
                {
                    "id": "brand_logo",
                    "kind": "logo_candidate",
                    "bbox": [-5, 8, 90, 58],
                    "confidence": 0.7,
                    "source_ids": ["shape_logo"],
                }
            ],
            "text_blocks": [],
            "shapes": [],
            "formulas": [],
            "charts": [],
            "connectors": [],
        },
    )

    slide = CandidateFusionProcessor().run(ctx)
    logo = next(element for element in slide.elements if element.id == "brand_logo")

    assert logo.type == ElementType.LOGO
    assert logo.asset_path == tmp_path / "assets" / "logos" / "brand_logo.png"
    assert logo.asset_path.exists()
    assert logo.bbox.x == 0
    assert logo.bbox.width == 90
    assert logo.provenance.raw["asset"]["kind"] == "logo"
    output = capsys.readouterr().out
    assert "[image2pptx][assets][saved]" in output
    manifest = json.loads((tmp_path / "assets" / "image_assets.json").read_text())
    assert manifest["candidate_count"] == 1
    assert manifest["items"][0]["asset_path"].endswith("assets/logos/brand_logo.png")


def test_candidate_fusion_writes_asset_manifest_when_no_image_regions(tmp_path, capsys):
    normalized = tmp_path / "normalized.png"
    Image.new("RGB", (300, 200), "white").save(normalized)
    ctx = SimpleNamespace(
        job_id="job_no_assets",
        job_dir=tmp_path,
        artifacts={"normalized": normalized},
        candidates={
            "layout_regions": [],
            "text_blocks": [],
            "shapes": [],
            "formulas": [],
            "charts": [],
            "connectors": [],
        },
    )

    CandidateFusionProcessor().run(ctx)

    output = capsys.readouterr().out
    manifest_path = tmp_path / "assets" / "image_assets.json"
    manifest = json.loads(manifest_path.read_text())
    assert "no image_candidate/logo_candidate/icon_candidate regions found" in output
    assert manifest["job_id"] == "job_no_assets"
    assert manifest["candidate_count"] == 0
    assert manifest["items"] == []
    assert ctx.artifacts["image_assets"] == manifest_path


def test_candidate_fusion_exports_icon_assets_separately(tmp_path):
    normalized = tmp_path / "normalized.png"
    Image.new("RGB", (240, 160), "white").save(normalized)
    ctx = SimpleNamespace(
        job_dir=tmp_path,
        artifacts={"normalized": normalized},
        candidates={
            "layout_regions": [
                {
                    "id": "icon_0",
                    "kind": "icon_candidate",
                    "bbox": [40, 35, 72, 67],
                    "confidence": 0.5,
                }
            ],
            "text_blocks": [],
            "shapes": [],
            "formulas": [],
            "charts": [],
            "connectors": [],
        },
    )

    slide = CandidateFusionProcessor().run(ctx)
    icon = next(element for element in slide.elements if element.id == "icon_0")

    assert icon.type == ElementType.ICON
    assert icon.asset_path == tmp_path / "assets" / "icons" / "icon_0.png"
    assert icon.asset_path.exists()
