from image2pptx.models.vlm import _build_headers, _parse_chat_json
from image2pptx.processors.vlm_arbitration import apply_vlm_arbitration


def test_vlm_headers_include_huawei_gateway_keys():
    headers = _build_headers({"x_hw_id": "id", "x_hw_appkey": "key"})

    assert headers["X-HW-ID"] == "id"
    assert headers["X-HW-APPKEY"] == "key"


def test_parse_openai_chat_json_content():
    body = '{"choices":[{"message":{"content":"{\\"items\\":[{\\"id\\":\\"a\\",\\"keep\\":false}]}"}}]}'

    assert _parse_chat_json(body)["items"][0]["id"] == "a"


def test_apply_vlm_arbitration_updates_layers_and_counts():
    layers = {
        "containers": [{"id": "c", "bbox": [0, 0, 100, 100]}],
        "texts": [{"id": "t", "bbox": [1, 1, 10, 10], "text": "x"}],
        "assets": [{"id": "a", "bbox": [20, 20, 30, 30]}],
        "connectors": [],
    }

    apply_vlm_arbitration(
        layers,
        {
            "items": [
                {
                    "id": "t",
                    "semantic_type": "label",
                    "parent_id": "c",
                    "style": {"font_color": "#ffffff"},
                },
                {"id": "a", "keep": False},
            ]
        },
    )

    assert layers["texts"][0]["semantic_type"] == "label"
    assert layers["texts"][0]["font_color"] == "#ffffff"
    assert layers["assets"] == []
    assert layers["counts"]["assets"] == 0
