import logging
import threading

from app.ai.ai_store import AiRuntime, EventStore
from app.config.config_store import ConfigStore, DEFAULT_CONFIG
from app.core.frame_buffer import FrameBuffer
from app.core.runtime import RecorderRuntime
from app.core.upload_stats import UploadStats
from app.web.webapp import create_app


def _make_test_client(tmp_path):
    cfg = DEFAULT_CONFIG.copy()
    cfg.update({
        "ai_provider": "openai",
        "ai_model": "gpt-vision-test",
        "ai_api_key": "sk-test",
        "ai_request_timeout_sec": 30,
    })

    app = create_app(
        cfg_store=ConfigStore(path=str(tmp_path / "config.json"), initial=cfg),
        frame_buf=FrameBuffer(),
        stats=UploadStats(),
        rec_rt=RecorderRuntime(),
        ai_rt=AiRuntime(),
        event_store=EventStore(path=str(tmp_path / "ai_events.jsonl")),
        logger=logging.getLogger("test-web-model-info"),
        stop_event=threading.Event(),
        threads={},
        server_log_path=str(tmp_path / "server.log"),
    )
    return app.test_client()


def test_ai_status_includes_safe_model_info(tmp_path):
    client = _make_test_client(tmp_path)

    resp = client.get("/api/ai/status")

    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["model_info"] == {
        "provider": "openai",
        "kind": "openai_compatible",
        "model": "gpt-vision-test",
        "base_url": "https://api.openai.com/v1",
        "timeout_sec": 30,
        "api_key_set": True,
    }


def test_dashboard_has_model_info_container(tmp_path):
    client = _make_test_client(tmp_path)

    resp = client.get("/dashboard")

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="aiModelInfo"' in html
    assert 'id="ai_provider"' in html
    assert 'id="ai_model"' in html
    assert 'id="ai_base_url"' in html
    assert 'id="ai_api_key"' in html
    assert 'id="ai_request_timeout_sec"' in html
    assert 'id="aiProviderHint"' in html
    assert "Model Info" in html


def test_config_update_accepts_provider_fields_and_masks_keys(tmp_path):
    client = _make_test_client(tmp_path)

    resp = client.put("/api/config", json={
        "ai_provider": "openai_compatible",
        "ai_model": "local-vision-test",
        "ai_base_url": "http://127.0.0.1:9000/v1",
        "ai_api_key": "local-secret",
        "ai_request_timeout_sec": 45,
        "ark_api_key": "legacy-secret",
    })

    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    cfg_resp = client.get("/api/config")
    assert cfg_resp.status_code == 200
    cfg = cfg_resp.get_json()
    assert cfg["ai_provider"] == "openai_compatible"
    assert cfg["ai_model"] == "local-vision-test"
    assert cfg["ai_base_url"] == "http://127.0.0.1:9000/v1"
    assert cfg["ai_request_timeout_sec"] == 45
    assert cfg["ai_api_key"] == "******"
    assert cfg["ark_api_key"] == "******"

    status_resp = client.get("/api/ai/status")
    assert status_resp.status_code == 200
    model_info = status_resp.get_json()["data"]["model_info"]
    assert model_info == {
        "provider": "openai_compatible",
        "kind": "openai_compatible",
        "model": "local-vision-test",
        "base_url": "http://127.0.0.1:9000/v1",
        "timeout_sec": 45,
        "api_key_set": True,
    }
