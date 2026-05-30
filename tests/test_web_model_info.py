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
    assert "Model Info" in html
