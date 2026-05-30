import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import pytest

from app.ai.vision_client import (
    OpenAICompatibleVisionClient,
    _extract_message_content,
    _join_chat_url,
    _normalize_ai_json,
    resolve_provider_settings,
    safe_provider_info,
)


class _FakeVisionHandler(BaseHTTPRequestHandler):
    seen = {}

    def log_message(self, format, *args):
        return

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        payload = json.loads(body.decode("utf-8"))

        _FakeVisionHandler.seen = {
            "path": self.path,
            "auth": self.headers.get("Authorization"),
            "model": payload.get("model"),
            "content": payload["messages"][0]["content"],
        }

        resp = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "has_person": True,
                            "person_count": 1,
                            "activity": "standing",
                            "risk_level": "info",
                            "summary": "fake response",
                            "confidence": 0.87,
                        })
                    }
                }
            ]
        }
        data = json.dumps(resp).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _serve_fake_vision():
    server = HTTPServer(("127.0.0.1", 0), _FakeVisionHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_openai_provider_uses_preset_base_url(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cfg = {
        "ai_provider": "openai",
        "ai_model": "gpt-vision-test",
        "ai_request_timeout_sec": 30,
    }

    settings = resolve_provider_settings(cfg)

    assert settings["kind"] == "openai_compatible"
    assert settings["base_url"] == "https://api.openai.com/v1"
    assert settings["api_key"] == "sk-test"
    assert settings["model"] == "gpt-vision-test"


def test_ark_keeps_legacy_model_and_key(monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    cfg = {
        "ai_provider": "ark",
        "ark_model": "doubao-test",
        "ark_api_key": "ark-test",
        "ai_request_timeout_sec": 30,
    }

    settings = resolve_provider_settings(cfg)

    assert settings["kind"] == "ark"
    assert settings["model"] == "doubao-test"
    assert settings["api_key"] == "ark-test"


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://api.example.com/v1", "https://api.example.com/v1/chat/completions"),
        ("https://api.example.com", "https://api.example.com/v1/chat/completions"),
        ("https://api.example.com/v1/chat/completions", "https://api.example.com/v1/chat/completions"),
    ],
)
def test_join_chat_url(base_url, expected):
    assert _join_chat_url(base_url) == expected


def test_extract_message_content_supports_string_and_parts():
    assert _extract_message_content({"choices": [{"message": {"content": "hello"}}]}) == "hello"
    assert _extract_message_content({
        "choices": [
            {
                "message": {
                    "content": [
                        {"type": "text", "text": "hello"},
                        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,x"}},
                        {"type": "text", "text": "world"},
                    ]
                }
            }
        ]
    }) == "hello\nworld"


def test_normalize_ai_json_clamps_confidence():
    obj = _normalize_ai_json({"has_person": 1, "confidence": 2})

    assert obj["has_person"] is True
    assert obj["confidence"] == 1.0
    assert obj["activity"] == "unknown"


def test_openai_compatible_client_requires_base_url():
    with pytest.raises(ValueError):
        OpenAICompatibleVisionClient(api_key="x", model="m", base_url="")


def test_safe_provider_info_hides_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    info = safe_provider_info({
        "ai_provider": "openai",
        "ai_model": "gpt-vision-test",
        "ai_request_timeout_sec": 30,
    })

    assert info["provider"] == "openai"
    assert info["api_key_set"] is True
    assert "api_key" not in info


def test_openai_compatible_client_can_analyze_frame_against_fake_server():
    server = _serve_fake_vision()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}/v1"
        client = OpenAICompatibleVisionClient(
            api_key="test-key",
            model="fake-vision-model",
            base_url=base_url,
            timeout_sec=5,
        )

        frame = np.zeros((16, 16, 3), dtype=np.uint8)
        result = client.analyze_frame(frame, time_text="2026-05-30 02:33:11")

        assert result["has_person"] is True
        assert result["person_count"] == 1
        assert result["activity"] == "standing"
        assert result["confidence"] == 0.87

        assert _FakeVisionHandler.seen["path"] == "/v1/chat/completions"
        assert _FakeVisionHandler.seen["auth"] == "Bearer test-key"
        assert _FakeVisionHandler.seen["model"] == "fake-vision-model"
        content = _FakeVisionHandler.seen["content"]
        assert content[0]["type"] == "text"
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    finally:
        server.shutdown()
        server.server_close()
