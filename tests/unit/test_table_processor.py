from types import SimpleNamespace

from image2pptx.processors.table_processor import TableProcessor, _cells_from_html


def test_table_processor_extracts_cells_from_html() -> None:
    ctx = SimpleNamespace(
        candidates={
            "layout_regions": [
                {
                    "id": "table_0",
                    "kind": "table_candidate",
                    "bbox": [0, 0, 100, 50],
                    "confidence": 0.5,
                    "raw": {
                        "html": """
                        <table>
                          <tr><th>Name</th><th>Amount</th></tr>
                          <tr><td>A</td><td>10</td></tr>
                        </table>
                        """,
                    },
                }
            ]
        }
    )

    TableProcessor().run(ctx)

    table = ctx.candidates["layout_regions"][0]
    assert table["rows"] == 2
    assert table["cols"] == 2
    assert table["cells"][0][0]["text"] == "Name"
    assert table["cells"][1][1]["text"] == "10"
    assert table["confidence"] == 0.75


def test_table_processor_normalizes_explicit_cells() -> None:
    ctx = SimpleNamespace(
        candidates={
            "layout_regions": [
                {
                    "kind": "table_candidate",
                    "raw": {
                        "table_res": {
                            "cells": [
                                {"row_idx": 0, "col_idx": 0, "content": "Q1"},
                                {"row_idx": 0, "col_idx": 1, "content": "Q2"},
                                {"row_idx": 1, "col_idx": 0, "text": "12"},
                                {"row_idx": 1, "col_idx": 1, "text": "18"},
                            ]
                        }
                    },
                }
            ]
        }
    )

    TableProcessor().run(ctx)

    table = ctx.candidates["layout_regions"][0]
    assert table["rows"] == 2
    assert table["cols"] == 2
    assert table["cells"][0][1]["text"] == "Q2"
    assert table["cells"][1][0]["text"] == "12"


def test_cells_from_html_preserves_colspan_grid_width() -> None:
    cells = _cells_from_html(
        "<table><tr><th colspan='2'>Header</th></tr><tr><td>A</td><td>B</td></tr></table>"
    )

    assert len(cells) == 2
    assert len(cells[0]) == 2
    assert cells[0][0]["text"] == "Header"
    assert cells[0][1] == {}
    assert cells[1][1]["text"] == "B"
