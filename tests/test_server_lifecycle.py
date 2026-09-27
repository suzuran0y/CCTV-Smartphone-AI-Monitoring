"""Exercise the real server entry point with disposable data and loopback HTTP."""
import http.cookiejar
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from app.core.auth import AuthStore
from app.config.config_store import ConfigStore, DEFAULT_CONFIG


def test_server_starts_authenticates_and_shuts_down(tmp_path):
    auth = AuthStore(tmp_path / "auth.sqlite3")
    token = auth.initialize()
    cfg = ConfigStore(str(tmp_path / "config.json"), {**DEFAULT_CONFIG, "out_root": str(tmp_path / "recordings")})
    assert cfg.save_to_disk()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    program = """
import sys
from pathlib import Path
import server
root = Path(sys.argv[1])
server.APP_CONFIG_DIR = str(root)
server.CONFIG_PATH = str(root / 'config.json')
server.SERVER_LOG_PATH = str(root / 'server.log')
server.AI_EVENTS_PATH = str(root / 'events.jsonl')
sys.argv = ['server.py', '--host', '127.0.0.1', '--port', sys.argv[2]]
server.main()
"""
    process = subprocess.Popen([sys.executable, "-c", program, str(tmp_path), str(port)],
                               cwd=str(Path(__file__).resolve().parents[1]),
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:%d" % port
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                         urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    try:
        deadline = time.monotonic() + 15
        while True:
            try:
                with opener.open(base + "/ping", timeout=1) as response:
                    assert response.read() == b"OK"
                break
            except urllib.error.URLError:
                assert time.monotonic() < deadline and process.poll() is None, "server did not start"
                time.sleep(.1)
        request = urllib.request.Request(base + "/api/auth/login", method="POST",
            data=json.dumps({"token": token}).encode(),
            headers={"Content-Type": "application/json", "X-Sentinel-Request": "1"})
        with opener.open(request, timeout=5) as response:
            csrf = json.load(response)["csrf"]
        request = urllib.request.Request(base + "/api/system/shutdown", method="POST", data=b"",
            headers={"X-Sentinel-Request": "1", "X-CSRF-Token": csrf})
        with opener.open(request, timeout=5) as response:
            assert json.load(response)["ok"]
        assert process.wait(timeout=8) == 0
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
