"""Sentinel command-line service; also used by the Windows desktop launcher."""
import argparse
import json
import os
import socket
import sys
import threading
from pathlib import Path

from werkzeug.serving import make_server

from app.ai.ai_monitor_worker import start_ai_monitor_thread
from app.ai.ai_store import AiRuntime, EventStore
from app.config.config_store import ConfigStore, DEFAULT_CONFIG
from app.core.auth import AuthStore
from app.core.frame_buffer import FrameBuffer
from app.core.instance_lock import instance_lock
from app.core.logger import setup_logger
from app.core.runtime import RecorderRuntime
from app.core.upload_stats import UploadStats
from app.recorder.recorder_worker import start_record_thread, stop_recorder
from app.version import SENTINEL_VERSION
from app.web.webapp import create_app

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "log")
APP_CONFIG_DIR = os.path.join(BASE_DIR, "app", "config")
SERVER_LOG_PATH = os.path.join(LOG_DIR, "server.log")
AI_EVENTS_PATH = os.path.join(LOG_DIR, "ai_events.jsonl")
CONFIG_PATH = os.path.join(APP_CONFIG_DIR, "config.json")


def get_local_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def desktop_event(event, **fields):
    print("SENTINEL_EVENT " + json.dumps({"event": event, **fields}), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset-admin-token", action="store_true", help="Reset local administrator token and exit")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--data-dir", type=Path, help="Writable root for settings, logs and relative output paths")
    parser.add_argument("--desktop-shell-port", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("invalid service port")
    if args.desktop_shell_port is not None and not 1 <= args.desktop_shell_port <= 65535:
        parser.error("invalid desktop shell port")
    root = args.data_dir.resolve() if args.data_dir else None
    config_dir = root / "app/config" if root else Path(APP_CONFIG_DIR)
    log_path = root / "log/server.log" if root else Path(SERVER_LOG_PATH)
    events_path = root / "log/ai_events.jsonl" if root else Path(AI_EVENTS_PATH)
    config_path = config_dir / "config.json" if root else Path(CONFIG_PATH)
    config_dir.mkdir(parents=True, exist_ok=True)
    with instance_lock(config_dir / ".sentinel-service.lock"):
        if root:
            os.chdir(root)
        run_service(args, config_dir, config_path, log_path, events_path)


def run_service(args, config_dir, config_path, log_path, events_path):
    desktop = args.desktop_shell_port is not None
    auth_store = AuthStore(str(config_dir / "auth.sqlite3"))
    token = auth_store.initialize(reset=args.reset_admin_token)
    if token:
        if desktop:
            desktop_event("token", token=token)
        else:
            print("Administrator token (shown once; store securely): " + token, flush=True)
    if args.reset_admin_token:
        print("Administrator sessions revoked. Camera pairings are unchanged.")
        return

    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = setup_logger(str(log_path))
    cfg_store = ConfigStore(path=str(config_path), initial=DEFAULT_CONFIG.copy())
    if not cfg_store.load_from_disk(logger):
        raise RuntimeError("Cannot load configuration; fix it before starting to preserve privacy settings.")
    stop_event = threading.Event()
    frame_buf = FrameBuffer()
    rec_rt = RecorderRuntime()
    ai_rt = AiRuntime()
    event_store = EventStore(str(events_path))
    threads = {}
    app = create_app(cfg_store, frame_buf, UploadStats(), rec_rt, ai_rt, event_store,
                     logger, stop_event, threads, str(log_path), auth_store=auth_store)
    try:
        http_server = make_server(args.host, args.port, app, threaded=True)
    except SystemExit as error:
        raise RuntimeError(f"Cannot listen on {args.host}:{args.port}; check whether the port is in use.") from error

    app.config["SERVER_SHUTDOWN"] = http_server.shutdown
    port = http_server.server_port
    local_ip = "127.0.0.1" if args.host == "127.0.0.1" else get_local_ip()
    if local_ip != "127.0.0.1":
        app.config["CAMFLOW_ADDRESS"] = f"{local_ip}:{port}"
    if desktop:
        app.config.update(DESKTOP_ORIGIN=f"http://127.0.0.1:{args.desktop_shell_port}",
                          DESKTOP_DASHBOARD_HOST=f"127.0.0.1:{port}")
    try:
        cfg_store.set_many({"ingest_enabled": False, "recording": False})
        if not cfg_store.save_to_disk(logger):
            raise RuntimeError("Cannot save startup configuration.")
        threads["record"] = start_record_thread(cfg_store, frame_buf, rec_rt, logger, stop_event)
        threads["ai"] = start_ai_monitor_thread(cfg_store, frame_buf, ai_rt, event_store, logger, stop_event)
        local_url = f"http://127.0.0.1:{port}/"
        if desktop:
            def wait_for_parent():
                # EOF means Stop or parent exit. Control never travels over the LAN.
                sys.stdin.read(1)
                http_server.shutdown()
            threading.Thread(target=wait_for_parent, name="desktop-control", daemon=True).start()
            desktop_event("ready", url=local_url, lan=f"{local_ip}:{port}")
        else:
            print(f"Sentinel v{SENTINEL_VERSION} Server Started\n Dashboard: {local_url}\n"
                  f" LAN Web: http://{local_ip}:{port}/\n CamFlow: {local_ip}:{port}\n"
                  " Default ingest: OFF (enable in dashboard)", flush=True)
        http_server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        cfg_store.set_many({"ingest_enabled": False, "recording": False})
        stop_recorder(rec_rt, logger)
        for worker in threads.values():
            worker.join(timeout=2)
        http_server.server_close()


if __name__ == "__main__":
    main()
