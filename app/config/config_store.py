# pc/app/config/config_store.py
import json
import os
import threading
import math
import re
from typing import Any, Dict, Optional, Tuple

# Optional placeholders (kept to preserve your original structure)
API_KEY = ""
DATABASE_URL = ""
DEBUG = True

DEFAULT_CONFIG: Dict[str, Any] = {
    # communication / ingest
    "ingest_enabled": False,  # default: do not accept phone uploads
    "autosave": False,
    "viewer_auth_required": False,
    "record_cleanup_enabled": False,
    "record_retention_days": 7,
    "record_max_storage_gb": 20,
    "record_min_free_gb": 1,

    # preview / stream
    "stream_fps": 10,
    "jpeg_quality": 80,

    # recording
    "recording": False,
    "record_fps": 10,
    "segment_seconds": 60,
    "out_root": "recordings",
    "cam_name": "phone1",
    "codec": "mp4v",

    # =========================
    # AI monitoring (triggered branch v1)
    # =========================
    "ai_enabled": False,
    "ai_mode": "triggered",

    # Ark / Volcengine
    "ai_provider": "ark",
    "ai_model": "",
    "ai_base_url": "",
    "ai_api_key": "",
    "ai_request_timeout_sec": 30,
    "ark_model": "doubao-seed-2-0-mini-260215",
    "ark_api_key": API_KEY,  # can also be supplied via env var ARK_API_KEY

    # intervals & thresholds
    "ai_interval_observe": 5,
    "ai_dwell_threshold_sec": 5,
    "ai_end_grace_sec": 3,

    # prompt contexts
    "ai_prompt_template": (
        "You are a video surveillance assistant. You will receive a single CCTV frame and some context. "
        "Output ONLY one JSON object that decides whether there is a person, the person count, the activity, "
        "the risk level, and a short summary."
    ),
    "ai_scene_profile": "none",
    "ai_session_focus": "none",
    "ai_prompt_extra": "none",
    "ai_jpeg_quality": 85,

    # trigger (motion sentinel)
    "motion_ratio_threshold": 0.02,
    "motion_min_interval": 1.0,
}


def merge_known_keys(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    merged = base.copy()
    for k, v in patch.items():
        if k in merged:
            merged[k] = v
    return merged


def validate_and_normalize(patch: dict) -> Tuple[bool, dict, str]:
    cleaned: Dict[str, Any] = {}

    def _int(name: str, lo: int, hi: int) -> None:
        if name not in patch:
            return
        try:
            v = int(patch[name])
        except Exception:
            raise ValueError(f"{name} must be int")
        if v < lo or v > hi:
            raise ValueError(f"{name} must be in [{lo}, {hi}]")
        cleaned[name] = v

    def _float(name: str, lo: float, hi: float) -> None:
        if name not in patch:
            return
        try:
            v = float(patch[name])
        except Exception:
            raise ValueError(f"{name} must be float")
        if not math.isfinite(v) or v < lo or v > hi:
            raise ValueError(f"{name} must be in [{lo}, {hi}]")
        cleaned[name] = v

    def _bool(name: str) -> None:
        if name not in patch:
            return
        v = patch[name]
        if isinstance(v, bool):
            cleaned[name] = v
            return
        if isinstance(v, str):
            if v.lower() in ("true", "1", "yes", "on"):
                cleaned[name] = True
                return
            if v.lower() in ("false", "0", "no", "off"):
                cleaned[name] = False
                return
        raise ValueError(f"{name} must be bool")

    def _str(name: str, maxlen: int = 200) -> None:
        if name not in patch:
            return
        v = str(patch[name])
        if len(v) > maxlen:
            raise ValueError(f"{name} too long")
        cleaned[name] = v

    try:
        if not isinstance(patch, dict):
            raise ValueError("configuration must be an object")
        _bool("autosave")
        _bool("ingest_enabled")
        _bool("viewer_auth_required")
        _bool("record_cleanup_enabled")
        _int("record_retention_days", 1, 3650)
        _float("record_max_storage_gb", 0.1, 100000)
        _float("record_min_free_gb", 0.1, 100000)

        _int("stream_fps", 1, 30)
        _int("jpeg_quality", 30, 95)

        _int("record_fps", 1, 30)
        _int("segment_seconds", 10, 3600)

        _str("out_root", 300)
        _str("cam_name", 80)
        _str("codec", 20)
        if "cam_name" in cleaned and not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", cleaned["cam_name"]):
            raise ValueError("cam_name must contain only letters, digits, underscores or hyphens")
        if "out_root" in cleaned:
            from app.recorder.storage import safe_root
            safe_root(cleaned["out_root"])

        # AI switches
        _bool("ai_enabled")
        _str("ai_mode", 30)
        _str("ai_provider", 50)
        _str("ai_model", 200)
        _str("ai_base_url", 300)
        _str("ai_api_key", 300)
        _int("ai_request_timeout_sec", 5, 120)

        # Ark config
        _str("ark_model", 200)
        _str("ark_api_key", 300)

        # AI intervals & thresholds
        _float("ai_interval_observe", 1, 60)
        _float("ai_dwell_threshold_sec", 1, 600)
        _float("ai_end_grace_sec", 0, 60)

        # Prompt contexts
        _str("ai_prompt_template", 2000)
        _str("ai_scene_profile", 2000)
        _str("ai_session_focus", 2000)
        _str("ai_prompt_extra", 4000)

        # JPEG quality
        _int("ai_jpeg_quality", 50, 95)

        # Motion trigger params
        _float("motion_ratio_threshold", 0.001, 0.5)
        _float("motion_min_interval", 0.1, 10.0)

    except Exception as e:
        return False, {}, str(e)

    return True, cleaned, ""


class ConfigStore:
    """Thread-safe config store with load/save and partial updates."""
    def __init__(self, path: str = "config.json", initial: Optional[Dict[str, Any]] = None):
        self.path = path
        self.lock = threading.Lock()
        self.config = initial or DEFAULT_CONFIG.copy()

    def get_copy(self) -> dict:
        with self.lock:
            return self.config.copy()

    def set_many(self, patch: dict) -> dict:
        with self.lock:
            self.config = merge_known_keys(self.config, patch)
            return self.config.copy()

    def set_key(self, key: str, val: Any) -> None:
        with self.lock:
            if key in self.config:
                self.config[key] = val

    def load_from_disk(self, logger=None) -> bool:
        if not os.path.exists(self.path):
            return True
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            ok, cleaned, err = validate_and_normalize(data)
            if not ok:
                raise ValueError(err)
            with self.lock:
                self.config = merge_known_keys(DEFAULT_CONFIG, cleaned)
            if logger:
                logger.info("config loaded from disk")
            return True
        except Exception as e:
            if logger:
                logger.error(f"load config failed: {e}")
            return False

    def save_to_disk(self, logger=None) -> bool:
        try:
            with self.lock:
                with open(self.path + ".tmp", "w", encoding="utf-8") as f:
                    json.dump(self.config, f, indent=2, ensure_ascii=False)
                os.replace(self.path + ".tmp", self.path)
            if logger:
                logger.info("config saved to disk")
            return True
        except Exception as e:
            if logger:
                logger.error(f"save config failed: {e}")
            return False
