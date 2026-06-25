from types import SimpleNamespace

from image2pptx.processors.chart_processor import ChartProcessor
from image2pptx.processors.formula_processor import FormulaProcessor, _looks_like_formula


def test_formula_processor_detects_formula_text_block():
    ctx = SimpleNamespace(
        candidates={
            "text_blocks": [
                {
                    "id": "text_block_0",
                    "text": "E = mc^2",
                    "bbox": [10, 10, 100, 30],
                    "confidence": 0.92,
                    "source_ids": ["text_0"],
                },
                {
                    "id": "text_block_1",
                    "text": "plain title",
                    "bbox": [10, 40, 100, 60],
                    "confidence": 0.95,
                },
            ]
        }
    )

    FormulaProcessor().run(ctx)

    assert _looks_like_formula("sum(x)/2") is True
    assert len(ctx.candidates["formulas"]) == 1
    assert ctx.candidates["formulas"][0]["text"] == "E = mc^2"


def test_chart_processor_detects_bottom_aligned_bars():
    ctx = SimpleNamespace(
        candidates={
            "shapes": [
                {"id": "bar_0", "bbox": [10, 60, 30, 120], "confidence": 0.6},
                {"id": "bar_1", "bbox": [40, 40, 60, 120], "confidence": 0.6},
                {"id": "bar_2", "bbox": [70, 80, 90, 120], "confidence": 0.6},
                {"id": "wide_box", "bbox": [120, 20, 300, 120], "confidence": 0.6},
            ]
        }
    )

    ChartProcessor().run(ctx)

    assert len(ctx.candidates["charts"]) == 1
    chart = ctx.candidates["charts"][0]
    assert chart["kind"] == "bar_chart"
    assert chart["categories"] == ["1", "2", "3"]
    assert chart["values"] == [0.75, 1.0, 0.5]
