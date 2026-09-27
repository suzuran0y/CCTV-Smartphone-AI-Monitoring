# pc/server.py
import os
import socket
import threading
import argparse

from app.core.logger import setup_logger
from app.core.frame_buffer import FrameBuffer
from app.core.upload_stats import UploadStats
from app.core.runtime import RecorderRuntime
from app.config.config_store import ConfigStore, DEFAULT_CONFIG
from app.recorder.recorder_worker import start_record_thread
from app.recorder.recorder_worker import stop_recorder
from werkzeug.serving import make_server
from app.ai.ai_store import AiRuntime, EventStore
from app.ai.ai_monitor_worker import start_ai_monitor_thread
from app.web.webapp import create_app
from app.version import SENTINEL_VERSION
from app.core.auth import AuthStore

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "log")
APP_CONFIG_DIR = os.path.join(BASE_DIR, "app", "config")
SERVER_LOG_PATH = os.path.join(LOG_DIR, "server.log")
AI_EVENTS_PATH = os.path.join(LOG_DIR, "ai_events.jsonl")
CONFIG_PATH = os.path.join(APP_CONFIG_DIR, "config.json")

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(APP_CONFIG_DIR, exist_ok=True)

def get_local_ip() -> str:
    """Best-effort LAN IP detection without sending traffic."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset-admin-token", action="store_true", help="Reset local administrator token and exit")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    auth_store = AuthStore(os.path.join(APP_CONFIG_DIR, "auth.sqlite3"))
    token = auth_store.initialize(reset=args.reset_admin_token)
    if token:
        print("Administrator token (shown once; store securely): " + token, flush=True)
    if args.reset_admin_token:
        print("Administrator sessions revoked. Camera pairings are unchanged.")
        return
    logger = setup_logger(SERVER_LOG_PATH)
    stop_event = threading.Event()
    host = args.host
    port = args.port

    cfg_store = ConfigStore(path=CONFIG_PATH, initial=DEFAULT_CONFIG.copy())
    frame_buf = FrameBuffer()
    stats = UploadStats()
    rec_rt = RecorderRuntime()

    # Load config before starting the UI session.
    if not cfg_store.load_from_disk(logger):
        raise RuntimeError("Cannot load configuration; fix it before starting to preserve privacy settings")

    # Force-reset on startup: open the web UI first, then enable ingest/recording manually from dashboard.
    cfg_store.set_key("ingest_enabled", False)
    cfg_store.set_key("recording", False)
    if not cfg_store.save_to_disk(logger):
        raise RuntimeError("Cannot save startup configuration")

    # Background recorder thread (original code starts it again; recorder_worker has an internal guard).
    record_thread = start_record_thread(cfg_store, frame_buf, rec_rt, logger, stop_event)

    # AI runtime + event store
    ai_rt = AiRuntime()
    event_store = EventStore(path=AI_EVENTS_PATH)

    # Background AI monitor thread (triggered mode)
    ai_thread = start_ai_monitor_thread(cfg_store, frame_buf, ai_rt, event_store, logger, stop_event)

    threads = {"record": record_thread, "ai": ai_thread}

    app = create_app(
        cfg_store=cfg_store,
        frame_buf=frame_buf,
        stats=stats,
        rec_rt=rec_rt,
        ai_rt=ai_rt,
        event_store=event_store,
        logger=logger,
        stop_event=stop_event,
        threads=threads,
        server_log_path=SERVER_LOG_PATH,
        auth_store=auth_store,
    )

    local_ip = get_local_ip()

    url_lan = f"http://{local_ip}:{port}/"
    url_local = f"http://127.0.0.1:{port}/"

    print("\n====================================================================")
    print(f" Sentinel v{SENTINEL_VERSION} Server Started")
    print(f" Dashboard:  {url_local}            open on this PC")
    print(f" LAN Web:    {url_lan}       open from other devices")
    print(f" CamFlow:    {local_ip}:{port}              enter this address manually in the app")
    print(" Default ingest: OFF (enable in dashboard)")
    print("====================================================================\n", flush=True)

    http_server = make_server(host, port, app, threaded=True)
    app.config["SERVER_SHUTDOWN"] = http_server.shutdown
    try:
        http_server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        cfg_store.set_key("recording", False)
        stop_recorder(rec_rt, logger)
        for worker in threads.values():
            worker.join(timeout=2)
        http_server.server_close()


if __name__ == "__main__":
    main()
