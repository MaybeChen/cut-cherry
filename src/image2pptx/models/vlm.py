"""OpenAI-compatible VLM adapter used for semantic arbitration.

The adapter is lazy/offline-safe and keeps provider details in configuration.  It
expects an OpenAI chat-completions compatible endpoint and supports Huawei Pangu
MAAS gateway headers through ``x_hw_id`` and ``x_hw_appkey`` config keys.
"""
from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class VlmAdapter:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def infer_json(self, messages: list[dict[str, Any]], *, max_tokens: int = 1200) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        if not bool(self.config.get("enabled", False)):
            return None, [{"reason": "vlm_disabled"}]
        base_url = str(self.config.get("base_url") or self.config.get("endpoint") or "").rstrip("/")
        model = self.config.get("model")
        if not base_url or not model:
            return None, [
                {
                    "reason": "vlm_not_configured",
                    "message": "Set models.vlm.base_url/endpoint and models.vlm.model to enable VLM arbitration.",
                }
            ]
        payload = {
            "model": model,
            "messages": messages,
            "temperature": float(self.config.get("temperature", 0.0)),
            "max_tokens": int(self.config.get("max_tokens", max_tokens)),
            "response_format": {"type": "json_object"},
        }
        url = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=_build_headers(self.config),
            method="POST",
        )
        timeout = int(self.config.get("timeout", 60))
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310 - configured internal gateway endpoint
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            return None, [{"reason": "vlm_http_error", "status": exc.code, "message": exc.read().decode("utf-8", errors="ignore")}]
        except URLError as exc:
            return None, [{"reason": "vlm_request_failed", "message": str(exc.reason)}]
        except TimeoutError as exc:
            return None, [{"reason": "vlm_timeout", "message": str(exc)}]
        try:
            return _parse_chat_json(body), []
        except (json.JSONDecodeError, KeyError, TypeError, IndexError) as exc:
            return None, [{"reason": "vlm_invalid_response", "message": str(exc), "body": body[:500]}]


def _build_headers(config: dict[str, Any]) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = config.get("api_key")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    x_hw_id = config.get("x_hw_id") or config.get("X-HW-ID")
    x_hw_appkey = config.get("x_hw_appkey") or config.get("X-HW-APPKEY")
    if x_hw_id:
        headers["X-HW-ID"] = str(x_hw_id)
    if x_hw_appkey:
        headers["X-HW-APPKEY"] = str(x_hw_appkey)
    extra_headers = config.get("headers") or {}
    if isinstance(extra_headers, dict):
        headers.update({str(key): str(value) for key, value in extra_headers.items() if value is not None})
    return headers


def _parse_chat_json(body: str) -> dict[str, Any]:
    response = json.loads(body)
    content = response["choices"][0]["message"]["content"]
    if isinstance(content, dict):
        return content
    text = str(content).strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return json.loads(text)
