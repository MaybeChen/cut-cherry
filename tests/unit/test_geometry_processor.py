import pytest

try:
    import cv2  # noqa: F401
except ImportError as exc:
    pytest.skip(f"cv2 unavailable: {exc}", allow_module_level=True)

import numpy as np

from image2pptx.processors.geometry_processor import _detect_lines, _should_drop_line


def test_geometry_drops_long_shape_edge_lines():
    shape = {"bbox": [100.0, 100.0, 500.0, 180.0]}

    assert _should_drop_line((100, 101, 500, 101), [shape], 1000, 600) is True


def test_geometry_keeps_short_non_axis_connector_line():
    assert _should_drop_line((100, 100, 130, 128), [], 1000, 600) is False


def test_detect_lines_limits_long_page_border_noise(monkeypatch):
    edges = np.zeros((600, 1000), dtype=np.uint8)
    raw = np.array([[[10, 5, 990, 5]], [[100, 100, 130, 128]]], dtype=np.int32)

    import image2pptx.processors.geometry_processor as geometry

    monkeypatch.setattr(geometry.cv2, "HoughLinesP", lambda *args, **kwargs: raw)

    lines = _detect_lines(edges, [], 1000, 600)

    assert lines == [{"id": "line_0", "points": [[100, 100], [130, 128]], "confidence": 0.6}]
