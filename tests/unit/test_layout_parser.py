from types import SimpleNamespace

from image2pptx.processors.layout_parser import LayoutParserProcessor, _merge_text_into_blocks


def test_merge_text_items_preserves_separate_visual_lines():
    blocks = _merge_text_into_blocks(
        [
            {"id": "text_0", "text": "Hello", "bbox": [10, 10, 50, 30], "confidence": 0.9},
            {"id": "text_1", "text": "World", "bbox": [60, 11, 110, 31], "confidence": 0.8},
            {"id": "text_2", "text": "Second line", "bbox": [10, 38, 120, 58], "confidence": 0.7},
        ]
    )

    assert len(blocks) == 2
    assert blocks[0]["text"] == "Hello World"
    assert blocks[0]["bbox"] == [10.0, 10.0, 110.0, 31.0]
    assert blocks[0]["source_ids"] == ["text_0", "text_1"]
    assert blocks[1]["text"] == "Second line"


def test_layout_parser_adds_text_blocks_and_table_candidate_for_real_grid(monkeypatch):
    monkeypatch.setattr("image2pptx.processors.layout_parser._run_layout_model", lambda ctx: ([], []))
    ctx = SimpleNamespace(
        candidates={
            "text": [
                {"id": "text_0", "text": "A", "bbox": [110, 110, 130, 125], "confidence": 0.9},
                {"id": "text_1", "text": "B", "bbox": [170, 110, 190, 125], "confidence": 0.9},
            ],
            "lines": [
                {"id": "h1", "points": [[100, 100], [220, 100]], "confidence": 0.6},
                {"id": "h2", "points": [[100, 150], [220, 150]], "confidence": 0.6},
                {"id": "h3", "points": [[100, 200], [220, 200]], "confidence": 0.6},
                {"id": "v1", "points": [[100, 100], [100, 200]], "confidence": 0.6},
                {"id": "v2", "points": [[160, 100], [160, 200]], "confidence": 0.6},
                {"id": "v3", "points": [[220, 100], [220, 200]], "confidence": 0.6},
            ],
            "shapes": [],
        }
    )

    LayoutParserProcessor().run(ctx)

    assert [block["text"] for block in ctx.candidates["text_blocks"]] == ["A B"]
    table = next(
        region for region in ctx.candidates["layout_regions"] if region["kind"] == "table_candidate"
    )
    assert table["rows"] == 2
    assert table["cols"] == 2
    assert table["cells"][0][0]["text"] == "A"
    assert table["cells"][0][1]["text"] == "B"


def test_layout_parser_does_not_turn_simple_frame_into_table(monkeypatch):
    monkeypatch.setattr("image2pptx.processors.layout_parser._run_layout_model", lambda ctx: ([], []))
    ctx = SimpleNamespace(
        candidates={
            "text": [
                {"id": "text_0", "text": "Title", "bbox": [110, 110, 150, 125], "confidence": 0.9},
            ],
            "lines": [
                {"id": "h1", "points": [[100, 100], [220, 100]], "confidence": 0.6},
                {"id": "h2", "points": [[100, 150], [220, 150]], "confidence": 0.6},
                {"id": "v1", "points": [[100, 100], [100, 150]], "confidence": 0.6},
                {"id": "v2", "points": [[220, 100], [220, 150]], "confidence": 0.6},
            ],
            "shapes": [],
        }
    )

    LayoutParserProcessor().run(ctx)

    assert not any(
        region["kind"] == "table_candidate" for region in ctx.candidates["layout_regions"]
    )


def test_layout_model_dependency_error_warning_mentions_paddlex_extra():
    from image2pptx.processors.layout_parser import _build_layout_model_error_warning

    warning = _build_layout_model_error_warning(
        RuntimeError("PP-StructureV3 requires additional dependencies")
    )

    assert warning["reason"] == "layout_model_missing_paddlex_extra"
    assert "paddlex[ocr]" in warning["remediation"]


def test_layout_model_chart_missing_warning_suggests_disabling_chart_recognition():
    from image2pptx.processors.layout_parser import _build_layout_model_error_warning

    warning = _build_layout_model_error_warning(
        RuntimeError("layout_chart_recognition_model_missing: chart_recognition_model")
    )

    assert warning["reason"] == "layout_chart_recognition_model_missing"
    assert "use_chart_recognition=false" in warning["remediation"]


def test_merge_keeps_rule_icon_when_model_only_reports_overlapping_text() -> None:
    from image2pptx.processors.layout_parser import _merge_model_and_rule_regions

    model_regions = [
        {
            "id": "layout_model_0",
            "kind": "paragraph",
            "bbox": [10, 10, 50, 50],
            "confidence": 0.7,
        }
    ]
    rule_regions = [
        {
            "id": "icon_candidate_0",
            "kind": "icon_candidate",
            "bbox": [12, 12, 48, 48],
            "confidence": 0.5,
        }
    ]

    merged = _merge_model_and_rule_regions(model_regions, rule_regions)

    assert [region["kind"] for region in merged] == ["paragraph", "icon_candidate"]


def test_visual_suppression_ignores_weak_single_character_ocr() -> None:
    from image2pptx.processors.layout_parser import _text_blocks_for_visual_suppression

    blocks = [
        {"id": "weak", "text": "o", "bbox": [10, 10, 30, 30], "confidence": 0.2},
        {"id": "real", "text": "Label", "bbox": [40, 10, 90, 30], "confidence": 0.9},
    ]

    filtered = _text_blocks_for_visual_suppression(blocks)

    assert [block["id"] for block in filtered] == ["real"]


def test_rule_layout_includes_sam3_visual_regions_before_text() -> None:
    from types import SimpleNamespace

    from image2pptx.processors.layout_parser import _build_rule_layout_regions

    ctx = SimpleNamespace(
        artifacts={},
        candidates={
            "sam3_regions": [
                {
                    "id": "sam3_icon_0",
                    "kind": "icon_candidate",
                    "bbox": [10, 10, 30, 30],
                    "confidence": 0.8,
                }
            ],
            "shapes": [],
            "lines": [],
        },
    )
    text_blocks = [
        {
            "id": "text_line_0",
            "kind": "text_line",
            "text": "Label",
            "bbox": [40, 10, 100, 30],
            "confidence": 0.9,
        }
    ]

    regions = _build_rule_layout_regions(ctx, text_blocks)

    assert [region["id"] for region in regions] == ["sam3_icon_0", "text_line_0"]


def test_merge_keeps_small_sam3_visual_inside_large_model_image() -> None:
    from image2pptx.processors.layout_parser import _merge_model_and_rule_regions

    model_regions = [
        {
            "id": "layout_model_0",
            "kind": "image_candidate",
            "bbox": [0, 0, 500, 300],
            "confidence": 0.8,
        }
    ]
    rule_regions = [
        {
            "id": "sam3_icon_0",
            "kind": "icon_candidate",
            "bbox": [40, 40, 80, 80],
            "confidence": 0.7,
        }
    ]

    merged = _merge_model_and_rule_regions(model_regions, rule_regions)

    assert [region["id"] for region in merged] == ["layout_model_0", "sam3_icon_0"]
