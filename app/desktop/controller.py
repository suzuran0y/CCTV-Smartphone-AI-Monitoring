import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener


class ServiceController:
    """Own one child and wait for its graceful exit before allowing another."""

    def __init__(self, command, data_dir, port, shell_port, *, host="0.0.0.0"):
        self.command = [*command, "--data-dir", str(data_dir), "--host", host,
                        "--port", str(port), "--desktop-shell-port", str(shell_port)]
        self.expected_url = f"http://127.0.0.1:{port}/"
        self.lock = threading.Lock()
        self.finished = threading.Event()
        self.finished.set()
        self.process = None
        self.accepting_starts = True
        self.status = "stopped"
        self.url = self.lan = self.token = self.error = ""

    def snapshot(self):
        with self.lock:
            return {key: getattr(self, key) for key in ("status", "url", "lan", "token", "error")}

    def start(self, reset=False):
        with self.lock:
            if not self.accepting_starts or not self.finished.is_set():
                return False
            self.finished.clear()
            self.status = "resetting" if reset else "starting"
            self.url = self.lan = self.error = ""
        threading.Thread(target=self._run, args=(reset,), name="desktop-service", daemon=True).start()
        return True

    def stop(self, *, final=False):
        with self.lock:
            if final:
                self.accepting_starts = False
            if self.finished.is_set():
                return
            self.status = "stopping"
            self.url = ""
            self._close_pipe()

    def forget_token(self):
        with self.lock:
            self.token = ""

    def _close_pipe(self):
        if self.process and not self.process.stdin.closed:
            try:
                self.process.stdin.close()
            except BrokenPipeError:
                pass  # The child has already closed its end.

    def _run(self, reset):
        code = 1
        process = None
        try:
            process = subprocess.Popen(
                self.command + (["--reset-admin-token"] if reset else []),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            with self.lock:
                self.process = process
                if self.status == "stopping":
                    self._close_pipe()
            with process.stdout as output:
                for line in output:
                    if not line.startswith("SENTINEL_EVENT "):
                        continue
                    try:
                        event = json.loads(line[len("SENTINEL_EVENT "):])
                    except ValueError:
                        continue
                    if event.get("event") == "ready" and event.get("url") == self.expected_url:
                        self._mark_ready(event)
                    else:
                        with self.lock:
                            if event.get("event") == "token":
                                self.token = event["token"]
                            if event.get("event") == "error":
                                self.error = event["message"]
            code = process.wait()
        except (OSError, KeyError, TypeError) as error:
            with self.lock:
                self.error = str(error)
        finally:
            with self.lock:
                self._close_pipe()
            # A controller error must not allow a new service while the old one still owns files.
            if process and process.poll() is None:
                code = process.wait()
            with self.lock:
                self.process = None
                self.url = self.lan = ""
                self.status = "stopped" if code == 0 and not self.error else "failed"
                if code != 0 and not self.error:
                    self.error = f"Sentinel service exited with code {code}. Check its log."
                self.finished.set()

    def _mark_ready(self, event):
        probe = build_opener(ProxyHandler({}))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with self.lock:
                if self.status != "starting":
                    return
            try:
                with probe.open(self.expected_url + "ping", timeout=0.5) as response:
                    if response.read(8) != b"OK":
                        break
                with self.lock:
                    if self.status == "starting":
                        self.url, self.lan = self.expected_url, event["lan"]
                        self.status = "running"
                return
            except OSError:
                time.sleep(0.1)
        with self.lock:
            if self.status == "starting":
                self.error = "The service did not respond to its startup check."
                self.status = "stopping"
                self._close_pipe()


def child_command(root):
    if getattr(sys, "frozen", False):
        return [sys.executable, "--service"]
    return [sys.executable, str(Path(root) / "sentinel_desktop.py"), "--service"]
