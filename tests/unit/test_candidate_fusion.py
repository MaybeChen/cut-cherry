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
    assert (tmp_path / "assets" / "image_candidate_0.png").exists()
