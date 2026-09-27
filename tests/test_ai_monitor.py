import logging
import threading
from types import SimpleNamespace

import numpy as np

from app.ai.ai_monitor_worker import ai_monitor_loop
from app.ai.ai_store import AiRuntime
from app.ai.vision_client import client_signature, _normalize_ai_json
from app.config.config_store import ConfigStore, DEFAULT_CONFIG


def run_monitor(results, *, change=None, config=None, factory=None):
    cfg = ConfigStore(initial={**DEFAULT_CONFIG, "ai_enabled": True, "ai_model": "fake",
                               "ai_api_key": "fake", "ai_interval_observe": 1,
                               "ai_dwell_threshold_sec": 2, "ai_end_grace_sec": 2, **(config or {})})
    runtime = AiRuntime()
    stop = threading.Event()
    events, calls = [], []
    clock = [100.0]
    ticks = [0]
    def wait(_):
        clock[0] += 1
        ticks[0] += 1
        if change:
            change(ticks[0], cfg)
        if ticks[0] >= len(results) + 2:
            stop.set()
    def analyze(*_, **__):
        calls.append(clock[0])
        value = results[min(len(calls) - 1, len(results) - 1)]
        if isinstance(value, Exception):
            raise value
        return {"has_person": value, "confidence": .8}
    frame = SimpleNamespace(get_copy=lambda: np.zeros((8, 8, 3), dtype=np.uint8), age_sec=lambda: 0)
    motion_count = [0]
    def check(_):
        motion_count[0] += 1
        return motion_count[0] == 1, .5
    ai_monitor_loop(cfg, frame, runtime, SimpleNamespace(add_event=events.append), logging.getLogger("ai-test"), stop,
                    clock=lambda: clock[0], wait=wait,
                    client_factory=factory or (lambda _: SimpleNamespace(analyze_frame=analyze)),
                    motion_factory=lambda: SimpleNamespace(check=check))
    return events, calls, runtime


def test_complete_event_dwell_and_grace():
    events, calls, _ = run_monitor([True, True, True, False, True, False, False, False])
    kinds = [e["kind"] for e in events]
    assert kinds[0] == "event_start"
    assert kinds.count("dwell_confirmed") == 1
    assert kinds[-1] == "event_end"
    assert events[-1]["dwell_confirmed"] is True
    assert len(calls) == 8


def test_timeout_is_recorded_and_monitor_recovers():
    events, calls, _ = run_monitor([TimeoutError("test timeout"), True, False, False, False])
    assert any(e["kind"] == "ai_error" for e in events)
    assert any(e["kind"] == "event_end" for e in events)
    assert len(calls) >= 4


def test_disabling_ai_ends_event_and_stops_calls():
    events, calls, runtime = run_monitor([True] * 5, change=lambda tick, cfg: cfg.set_key("ai_enabled", False) if tick == 2 else None)
    assert len(calls) == 1
    assert events[-1]["reason"] == "disabled"
    assert runtime.state == "SLEEP"


def test_missing_config_does_not_call_model(monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    events, calls, runtime = run_monitor([True], config={"ai_api_key": "", "ark_api_key": ""})
    assert not events and not calls
    assert "api_key" in runtime.last_ai_error


def test_client_recreated_after_key_rotation():
    created = []
    def factory(cfg):
        created.append(cfg["ai_api_key"])
        return SimpleNamespace(analyze_frame=lambda *a, **k: {"has_person": True})
    run_monitor([True] * 4, change=lambda tick, cfg: cfg.set_key("ai_api_key", "replacement") if tick == 2 else None, factory=factory)
    assert created == ["fake", "replacement"]
    assert "replacement" not in client_signature({"ai_api_key": "replacement"})


def test_string_false_is_not_a_person():
    assert _normalize_ai_json({"has_person": "false"})["has_person"] is False
