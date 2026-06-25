from types import SimpleNamespace

from image2pptx.processors.layout_parser import LayoutParserProcessor, _merge_text_into_blocks


def test_merge_text_items_into_paragraph_block():
    blocks = _merge_text_into_blocks(
        [
            {"id": "text_0", "text": "Hello", "bbox": [10, 10, 50, 30], "confidence": 0.9},
            {"id": "text_1", "text": "World", "bbox": [60, 11, 110, 31], "confidence": 0.8},
            {"id": "text_2", "text": "Second line", "bbox": [10, 38, 120, 58], "confidence": 0.7},
        ]
    )

    assert len(blocks) == 1
    assert blocks[0]["text"] == "Hello World\nSecond line"
    assert blocks[0]["bbox"] == [10.0, 10.0, 120.0, 58.0]
    assert blocks[0]["source_ids"] == ["text_0", "text_1", "text_2"]


def test_layout_parser_adds_text_blocks_and_table_candidate():
    ctx = SimpleNamespace(
        candidates={
            "text": [
                {"id": "text_0", "text": "A", "bbox": [110, 110, 130, 125], "confidence": 0.9},
                {"id": "text_1", "text": "B", "bbox": [110, 132, 130, 147], "confidence": 0.9},
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

    assert ctx.candidates["text_blocks"][0]["text"] == "A\nB"
    table = next(
        region for region in ctx.candidates["layout_regions"] if region["kind"] == "table_candidate"
    )
    assert table["rows"] == 1
    assert table["cols"] == 1
    assert table["cells"][0][0]["text"] == "A\nB"
