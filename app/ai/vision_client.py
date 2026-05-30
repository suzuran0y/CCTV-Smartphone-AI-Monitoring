# pc/app/ai/vision_client.py
import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from .ai_ark import (
    ArkVisionClient,
    _extract_json,
    _frame_to_data_url_jpeg,
    _resize_for_ai,
    resolve_api_key,
)


PROVIDER_PRESETS: Dict[str, Dict[str, Any]] = {
    "openai": {
        "kind": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "env_keys": ["OPENAI_API_KEY"],
    },
    "dashscope": {
        "kind": "openai_compatible",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "env_keys": ["DASHSCOPE_API_KEY", "QWEN_API_KEY"],
    },
    "gemini": {
        "kind": "openai_compatible",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "env_keys": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    },
    "siliconflow": {
        "kind": "openai_compatible",
        "base_url": "https://api.siliconflow.cn/v1",
        "env_keys": ["SILICONFLOW_API_KEY"],
    },
    "openai_compatible": {
        "kind": "openai_compatible",
        "base_url": "",
        "env_keys": ["AI_API_KEY", "OPENAI_API_KEY"],
    },
    "ark": {
        "kind": "ark",
        "base_url": "",
        "env_keys": ["ARK_API_KEY"],
    },
}


def _clean_provider(provider: Any) -> str:
    name = str(provider or "ark").strip().lower().replace("-", "_")
    return name or "ark"


def _first_env(names: List[str]) -> str:
    for name in names:
        val = os.environ.get(name)
        if val:
            return val.strip()
    return ""


def _join_chat_url(base_url: str) -> str:
    base = str(base_url or "").strip()
    if not base:
        raise ValueError("ai_base_url is required for openai_compatible provider")
    base = base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def resolve_provider_settings(cfg: Dict[str, Any]) -> Dict[str, Any]:
    provider = _clean_provider(os.environ.get("AI_PROVIDER") or cfg.get("ai_provider") or "ark")
    preset = PROVIDER_PRESETS.get(provider)
    if preset is None:
        if provider == "volcengine":
            provider = "ark"
            preset = PROVIDER_PRESETS[provider]
        else:
            preset = PROVIDER_PRESETS["openai_compatible"]

    kind = preset["kind"]
    model = str(os.environ.get("AI_MODEL") or cfg.get("ai_model") or "").strip()
    base_url = str(os.environ.get("AI_BASE_URL") or cfg.get("ai_base_url") or preset.get("base_url") or "").strip()
    api_key = str(os.environ.get("AI_API_KEY") or cfg.get("ai_api_key") or "").strip()
    if not api_key:
        api_key = _first_env(list(preset.get("env_keys") or []))

    if kind == "ark":
        model = model or str(cfg.get("ark_model", "")).strip()
        api_key = api_key or resolve_api_key(cfg).strip()
        base_url = base_url or "https://ark.cn-beijing.volces.com/api/v3"

    timeout_sec = cfg.get("ai_request_timeout_sec", 30)
    try:
        timeout_sec = int(timeout_sec)
    except Exception:
        timeout_sec = 30
    timeout_sec = max(5, min(120, timeout_sec))

    return {
        "provider": provider,
        "kind": kind,
        "model": model,
        "base_url": base_url,
        "api_key": api_key,
        "timeout_sec": timeout_sec,
    }


def safe_provider_info(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Return current effective model settings without exposing API keys."""
    settings = resolve_provider_settings(cfg)
    return {
        "provider": settings["provider"],
        "kind": settings["kind"],
        "model": settings["model"],
        "base_url": settings["base_url"],
        "timeout_sec": settings["timeout_sec"],
        "api_key_set": bool(settings["api_key"]),
    }


class OpenAICompatibleVisionClient:
    """
    Vision client for providers that expose OpenAI-compatible Chat Completions.

    Supported examples include OpenAI, DashScope compatible mode, Gemini OpenAI
    compatibility, SiliconFlow, and other services exposing /v1/chat/completions.
    """

    def __init__(self, api_key: str, model: str, base_url: str, timeout_sec: int = 30):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout_sec = timeout_sec
        self.chat_url = _join_chat_url(base_url)

    @staticmethod
    def build_prompt_contract() -> str:
        return ArkVisionClient.build_prompt_contract()

    def analyze_frame(
        self,
        frame_bgr,
        time_text: str,
        prompt_template: str = "",
        scene_profile: str = "",
        session_focus: str = "",
        extra_prompt: str = "",
        jpeg_quality: int = 85,
        max_w: int = 640,
    ) -> Dict[str, Any]:
        frame_bgr = _resize_for_ai(frame_bgr, max_w=max_w)
        data_url = _frame_to_data_url_jpeg(frame_bgr, jpeg_quality=jpeg_quality)

        prompt_parts = [f"Current time: {time_text}"]
        if prompt_template:
            prompt_parts.append(f"Role: {prompt_template}")
        if scene_profile:
            prompt_parts.append(f"Long-term scene profile: {scene_profile}")
        if session_focus:
            prompt_parts.append(f"Session focus: {session_focus}")
        if extra_prompt:
            prompt_parts.append(f"Extra rules/notes: {extra_prompt}")
        prompt_parts.append(self.build_prompt_contract())
        prompt_parts.append("Based on the CCTV frame, output the JSON now.")

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "\n\n".join(prompt_parts)},
                        {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
                    ],
                }
            ],
        }

        req = urllib.request.Request(
            self.chat_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{e.code} from vision provider: {err_body[:500]}") from e

        data = json.loads(body)
        out_text = _extract_message_content(data)
        parsed = _extract_json(out_text)
        return _normalize_ai_json(parsed)


def _extract_message_content(data: Dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("provider response has no choices")

    msg = (choices[0] or {}).get("message") or {}
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join(parts)
    return str(content)


def _normalize_ai_json(parsed: Dict[str, Any]) -> Dict[str, Any]:
    parsed = dict(parsed or {})
    parsed.setdefault("has_person", False)
    parsed.setdefault("person_count", None)
    parsed.setdefault("activity", "unknown")
    parsed.setdefault("risk_level", "info")
    parsed.setdefault("summary", "")
    parsed.setdefault("confidence", 0.0)

    parsed["has_person"] = bool(parsed.get("has_person", False))
    try:
        c = float(parsed.get("confidence", 0.0) or 0.0)
        parsed["confidence"] = max(0.0, min(1.0, c))
    except Exception:
        parsed["confidence"] = 0.0
    return parsed


def create_vision_client(cfg: Dict[str, Any]):
    settings = resolve_provider_settings(cfg)
    if not settings["model"]:
        raise ValueError("AI model is required")
    if not settings["api_key"]:
        raise ValueError("AI API key is required")

    if settings["kind"] == "ark":
        return ArkVisionClient(
            api_key=settings["api_key"],
            model=settings["model"],
            timeout_sec=settings["timeout_sec"],
            base_url=settings["base_url"],
        )

    return OpenAICompatibleVisionClient(
        api_key=settings["api_key"],
        model=settings["model"],
        base_url=settings["base_url"],
        timeout_sec=settings["timeout_sec"],
    )


def client_signature(cfg: Dict[str, Any]) -> str:
    settings = resolve_provider_settings(cfg)
    return "|".join([
        settings["provider"],
        settings["kind"],
        settings["model"],
        settings["base_url"],
        "key" if settings["api_key"] else "nokey",
        str(settings["timeout_sec"]),
    ])
